import base64
import secrets
from datetime import date, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func, or_

from ..extensions import db
from ..models import (
    Categoria,
    IngresoStock,
    ConfigMarkup,
    ConsumoOT,
    FotoRepuesto,
    IngresoStockItem,
    MovimientoStock,
    PresupuestoItem,
    Proveedor,
    Repuesto,
    Subcategoria,
    VentaItem,
)
from ..services import drive
from ..services.stock import (
    anular_ingreso, buscar_repuesto, confirmar_ingreso, recalcular_precio_venta, regla_markup, registrar_movimiento,
)
from ..validaciones import numero_ar

bp = Blueprint("stock", __name__)

CAMPOS_TEXTO = ["nombre", "marca", "nro_parte", "codigo_barras", "proveedor", "cod_proveedor", "marca_proveedor",
                "comp_marca", "comp_modelo", "comp_motor", "detalle", "estanteria", "estante"]


@bp.before_request
@login_required
def _requiere_login():
    pass


def _texto(campo):
    return request.form.get(campo, "").strip() or None


def _distintos(columna):
    return sorted({v for (v,) in db.session.query(columna).distinct() if v}, key=str.lower)


def _proveedores():
    return [p.nombre for p in Proveedor.query.order_by(func.lower(Proveedor.nombre)).all()]


def _arbol_categorias():
    """Categorías con sus subcategorías, para los desplegables (la subcategoría depende de la categoría)."""
    return [{"id": c.id, "nombre": c.nombre, "subs": [{"id": sc.id, "nombre": sc.nombre} for sc in c.subcategorias]}
            for c in Categoria.query.order_by(Categoria.nombre).all()]


# ─────────────────────────────────── Repuestos ──────────────────────────────


# Campos de texto del repuesto donde busca el buscador (además de categoría, subcategoría y número)
CAMPOS_BUSQUEDA = [
    Repuesto.nombre, Repuesto.marca, Repuesto.nro_parte, Repuesto.codigo_barras, Repuesto.detalle,
    Repuesto.proveedor, Repuesto.cod_proveedor, Repuesto.marca_proveedor,
    Repuesto.comp_marca, Repuesto.comp_modelo, Repuesto.comp_motor, Repuesto.estanteria, Repuesto.estante,
]


def _coincide(palabra):
    """La palabra aparece en algún campo del repuesto, en su categoría o subcategoría, o es su número."""
    like = f"%{palabra}%"
    condiciones = [c.ilike(like) for c in CAMPOS_BUSQUEDA]
    condiciones.append(Repuesto.categoria_id.in_(db.session.query(Categoria.id).filter(Categoria.nombre.ilike(like))))
    condiciones.append(Repuesto.subcategoria_id.in_(
        db.session.query(Subcategoria.id).filter(Subcategoria.nombre.ilike(like))))
    if palabra.isdigit():
        condiciones.append(Repuesto.id == int(palabra))
    return or_(*condiciones)


# Columnas por las que se puede ordenar el listado (clave del encabezado → columna)
ORDENES = {
    "material": Repuesto.nombre, "marca": Repuesto.marca, "parte": Repuesto.nro_parte, "stock": Repuesto.stock_actual,
    "ubicacion": Repuesto.estanteria, "costo": Repuesto.precio_costo, "venta": Repuesto.precio_venta,
    "comp_marca": Repuesto.comp_marca, "comp_modelo": Repuesto.comp_modelo, "comp_motor": Repuesto.comp_motor,
    "detalle": Repuesto.detalle, "descuento": Repuesto.descuento_oferta, "cod_prov": Repuesto.cod_proveedor,
    "proveedor": Repuesto.proveedor, "categoria": Categoria.nombre, "subcategoria": Subcategoria.nombre,
}


def _ordenar(consulta, orden, direccion):
    """Ordena por la columna elegida; los vacíos siempre al final. Desempata por número de repuesto."""
    columna = ORDENES.get(orden)
    if columna is None:
        return consulta.order_by(Repuesto.id)
    if orden == "categoria":
        consulta = consulta.outerjoin(Categoria, Repuesto.categoria_id == Categoria.id)
    elif orden == "subcategoria":
        consulta = consulta.outerjoin(Subcategoria, Repuesto.subcategoria_id == Subcategoria.id)
    valor = func.lower(columna) if orden in ("material", "marca", "proveedor", "detalle") else columna
    extra = [Repuesto.estante] if orden == "ubicacion" else []
    if direccion == "desc":
        return consulta.order_by(columna.is_(None), valor.desc(), *[e.desc() for e in extra], Repuesto.id)
    return consulta.order_by(columna.is_(None), valor, *extra, Repuesto.id)


@bp.route("/")
def lista():
    q = request.args.get("q", "").strip()
    categoria_id = request.args.get("categoria", type=int)
    subcategoria_id = request.args.get("subcategoria", type=int)
    filtro = request.args.get("filtro", "")
    orden = request.args.get("orden", "")
    direccion = "desc" if request.args.get("dir") == "desc" else "asc"
    consulta = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS)
    if q:
        for palabra in q.split():  # todas las palabras tienen que aparecer en algún campo
            consulta = consulta.filter(_coincide(palabra))
    if categoria_id:
        consulta = consulta.filter(Repuesto.categoria_id == categoria_id)
    if subcategoria_id:
        consulta = consulta.filter(Repuesto.subcategoria_id == subcategoria_id)
    if filtro == "sin_stock":
        consulta = consulta.filter(Repuesto.stock_actual <= 0)
    elif filtro == "con_stock":
        consulta = consulta.filter(Repuesto.stock_actual > 0)
    elif filtro == "bajo":
        consulta = consulta.filter(Repuesto.stock_actual <= func.coalesce(Repuesto.stock_minimo, 0))
    repuestos = _ordenar(consulta, orden, direccion).all()
    plantilla = "stock/_tabla.html" if request.headers.get("HX-Request") else "stock/lista.html"
    return render_template(plantilla, repuestos=repuestos, q=q, arbol=_arbol_categorias(),
                           categoria_id=categoria_id, subcategoria_id=subcategoria_id, filtro=filtro,
                           orden=orden if orden in ORDENES else "", direccion=direccion)


@bp.route("/nuevo", methods=["GET", "POST"])
@bp.route("/<int:id>", methods=["GET", "POST"])
def ficha(id=None):
    if id == Repuesto.ID_VARIOS:
        flash("«Varios / Mano de Obra» es un ítem del sistema y no se edita.", "info")
        return redirect(url_for(".lista"))
    repuesto = db.get_or_404(Repuesto, id) if id else Repuesto(stock_actual=0)

    if request.method == "POST":
        errores = []
        for campo in CAMPOS_TEXTO:
            setattr(repuesto, campo, _texto(campo))
        costo = numero_ar(request.form.get("costo_lista"))
        repuesto.costo_lista = costo or 0
        repuesto.costo_manual = bool(request.form.get("costo_manual"))
        repuesto.markup = numero_ar(request.form.get("markup")) or None
        descuento = numero_ar(request.form.get("descuento_oferta"))
        repuesto.descuento_oferta = (descuento / 100) if descuento else None
        repuesto.stock_minimo = numero_ar(request.form.get("stock_minimo")) or 0
        repuesto.categoria = db.session.get(Categoria, request.form.get("categoria_id", type=int) or 0)
        sub = db.session.get(Subcategoria, request.form.get("subcategoria_id", type=int) or 0)
        repuesto.subcategoria = sub if sub and repuesto.categoria and sub.categoria_id == repuesto.categoria.id else None
        if repuesto.proveedor and repuesto.proveedor not in _proveedores():
            errores.append(f"El proveedor «{repuesto.proveedor}» no está en la lista: agregalo con el +.")
        if not repuesto.nombre:
            errores.append("El nombre es obligatorio.")
        if costo is None or costo < 0:
            errores.append("Poné el costo (puede ser 0).")
        if repuesto.markup is not None and repuesto.markup < 1:
            errores.append("El markup es un multiplicador: 1,4 = 40 % sobre el costo.")
        if repuesto.descuento_oferta and not 0 < repuesto.descuento_oferta < 1:
            errores.append("El descuento va en porcentaje, entre 0 y 100.")
        if errores:
            db.session.rollback()
            for e in errores:
                flash(e, "error")
        else:
            nuevo = not repuesto.id
            if nuevo:
                ultimo = db.session.query(func.max(Repuesto.id)).scalar() or 999
                repuesto.id = max(ultimo + 1, 1000)
                db.session.add(repuesto)
                inicial = numero_ar(request.form.get("stock_inicial")) or 0
                if inicial:
                    db.session.flush()
                    registrar_movimiento(repuesto, inicial, "Ajuste", detalle="Stock inicial")
            recalcular_precio_venta(repuesto)
            db.session.commit()
            flash(f"Repuesto #{repuesto.id} {'creado' if nuevo else 'guardado'}.", "ok")
            return redirect(url_for(".ficha", id=repuesto.id))

    markup, origen = regla_markup(repuesto) if repuesto.proveedor or repuesto.markup else (1.0, "sin regla de markup")
    movimientos = (MovimientoStock.query.filter_by(repuesto_id=repuesto.id).order_by(MovimientoStock.fecha.desc())
                   .limit(50).all() if repuesto.id else [])
    return render_template(
        "stock/ficha.html", r=repuesto, movimientos=movimientos, markup_actual=markup, origen_markup=origen,
        arbol=_arbol_categorias(),
        proveedores=_proveedores(), marcas=_distintos(Repuesto.marca),
        estanterias=_distintos(Repuesto.estanteria), estantes=_distintos(Repuesto.estante),
        reglas=[{"proveedor": m.proveedor, "marca": m.marca_envase, "markup": m.markup} for m in ConfigMarkup.query.all()],
        usado=_en_uso(repuesto) if repuesto.id else False,
    )


def _en_uso(repuesto):
    return any(model.query.filter_by(repuesto_id=repuesto.id).first()
               for model in (ConsumoOT, VentaItem, IngresoStockItem, PresupuestoItem, MovimientoStock))


@bp.route("/<int:id>/ajuste", methods=["POST"])
def ajuste(id):
    repuesto = db.get_or_404(Repuesto, id)
    nuevo = numero_ar(request.form.get("stock_nuevo"))
    motivo = request.form.get("motivo", "").strip()
    if nuevo is None or nuevo < 0:
        flash("Poné la cantidad que hay realmente en el taller.", "error")
    elif not motivo:
        flash("Contá el motivo del ajuste (ej.: conteo, rotura, devolución).", "error")
    elif nuevo == repuesto.stock_actual:
        flash("El stock ya era ese: no hubo cambios.", "info")
    else:
        diferencia = nuevo - repuesto.stock_actual
        registrar_movimiento(repuesto, diferencia, "Ajuste", detalle=f"Ajuste: {motivo}")
        db.session.commit()
        flash(f"Stock ajustado a {nuevo:g} ({'+' if diferencia > 0 else ''}{diferencia:g}).", "ok")
    return redirect(url_for(".ficha", id=id) + "#stock")


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    repuesto = db.get_or_404(Repuesto, id)
    if id == Repuesto.ID_VARIOS or _en_uso(repuesto):
        flash("No se puede eliminar: tiene movimientos, OT, ventas o compras asociadas.", "error")
        return redirect(url_for(".ficha", id=id))
    for foto in repuesto.fotos:
        if foto.drive_id:
            try:
                drive.llamar("borrar_foto", id=foto.drive_id)
            except drive.ErrorDrive:
                pass  # la foto queda en Drive; el repuesto se borra igual
    db.session.delete(repuesto)
    db.session.commit()
    flash(f"Repuesto #{id} eliminado.", "ok")
    return redirect(url_for(".lista"))


# ─────────────────────────── Categorías (alta rápida) ────────────────────────


@bp.route("/categorias", methods=["POST"])
def categoria_nueva():
    nombre = request.form.get("nombre", "").strip().upper()
    if not nombre:
        return jsonify(ok=False, error="Escribí el nombre."), 400
    if Categoria.query.filter(func.upper(Categoria.nombre) == nombre).first():
        return jsonify(ok=False, error=f"La categoría {nombre} ya existe."), 400
    cat = Categoria(nombre=nombre)
    db.session.add(cat)
    db.session.commit()
    return jsonify(ok=True, id=cat.id, nombre=cat.nombre)


@bp.route("/proveedores", methods=["POST"])
def proveedor_nuevo():
    nombre = " ".join(request.form.get("nombre", "").split())
    if not nombre:
        return jsonify(ok=False, error="Escribí el nombre."), 400
    if Proveedor.query.filter(func.lower(Proveedor.nombre) == nombre.lower()).first():
        return jsonify(ok=False, error=f"El proveedor {nombre} ya existe."), 400
    db.session.add(Proveedor(nombre=nombre))
    db.session.commit()
    return jsonify(ok=True, id=nombre, nombre=nombre)


@bp.route("/subcategorias", methods=["POST"])
def subcategoria_nueva():
    nombre = request.form.get("nombre", "").strip().upper()
    cat = db.session.get(Categoria, request.form.get("categoria_id", type=int) or 0)
    if not nombre or cat is None:
        return jsonify(ok=False, error="Elegí la categoría y escribí el nombre."), 400
    if Subcategoria.query.filter(Subcategoria.categoria_id == cat.id, func.upper(Subcategoria.nombre) == nombre).first():
        return jsonify(ok=False, error=f"{nombre} ya existe en {cat.nombre}."), 400
    sub = Subcategoria(nombre=nombre, categoria=cat)
    db.session.add(sub)
    db.session.commit()
    return jsonify(ok=True, id=sub.id, nombre=sub.nombre)


# ─────────────────────────────── Fotos del repuesto ─────────────────────────


@bp.route("/<int:id>/fotos", methods=["POST"])
def foto_subir(id):
    repuesto = db.get_or_404(Repuesto, id)
    archivo = request.files.get("imagen")
    datos = archivo.read() if archivo else b""
    if not datos.startswith(b"\xff\xd8"):
        return jsonify(ok=False, error="La imagen no llegó bien. Probá de nuevo."), 400
    nombre = f"REP{repuesto.id}_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(3)}.jpg"
    try:
        guardada = drive.llamar("foto", nombre=nombre, contenido=base64.b64encode(datos).decode(), subcarpeta="Repuestos")
    except drive.ErrorDrive as e:
        return jsonify(ok=False, error=str(e)), 502
    foto = FotoRepuesto(repuesto=repuesto, archivo=guardada.get("nombre", nombre), drive_id=guardada["id"],
                        descripcion=request.form.get("descripcion", "").strip()[:200] or None)
    db.session.add(foto)
    db.session.commit()
    return jsonify(ok=True, id=foto.id, miniatura=foto.miniatura)


@bp.route("/fotos/<int:fid>/editar", methods=["POST"])
def foto_editar(fid):
    foto = db.get_or_404(FotoRepuesto, fid)
    foto.descripcion = request.form.get("descripcion", "").strip()[:200] or None
    db.session.commit()
    return redirect(url_for(".ficha", id=foto.repuesto_id) + "#fotos")


@bp.route("/fotos/<int:fid>/eliminar", methods=["POST"])
def foto_eliminar(fid):
    foto = db.get_or_404(FotoRepuesto, fid)
    repuesto_id = foto.repuesto_id
    if foto.drive_id:
        try:
            drive.llamar("borrar_foto", id=foto.drive_id)
        except drive.ErrorDrive as e:
            flash(f"No pude borrar la foto en Drive: {e}", "error")
            return redirect(url_for(".ficha", id=repuesto_id) + "#fotos")
    db.session.delete(foto)
    db.session.commit()
    flash("Foto eliminada.", "ok")
    return redirect(url_for(".ficha", id=repuesto_id) + "#fotos")


# ──────────────────────────────────── Markups ───────────────────────────────


@bp.route("/markups", methods=["GET", "POST"])
def markups():
    if request.method == "POST":
        proveedor = request.form.get("proveedor", "").strip()
        marca = request.form.get("marca_envase", "").strip() or None
        markup = numero_ar(request.form.get("markup"))
        if proveedor not in _proveedores():
            flash("Elegí un proveedor de la lista.", "error")
        elif not markup or markup < 1:
            flash("Completá proveedor y un markup de 1 o más (1,4 = 40 %).", "error")
        elif ConfigMarkup.query.filter_by(proveedor=proveedor, marca_envase=marca).first():
            flash("Ya hay una regla para ese proveedor y marca: editala.", "error")
        else:
            db.session.add(ConfigMarkup(proveedor=proveedor, marca_envase=marca, markup=markup))
            db.session.commit()
            flash("Regla agregada. Tocá «Recalcular precios» para aplicarla.", "ok")
        return redirect(url_for(".markups"))
    reglas = ConfigMarkup.query.order_by(ConfigMarkup.proveedor, ConfigMarkup.marca_envase).all()
    uso = {}
    for r in Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS, Repuesto.markup.is_(None)).all():
        _, origen = regla_markup(r)
        uso[origen] = uso.get(origen, 0) + 1
    return render_template("stock/markups.html", reglas=reglas, uso=uso, proveedores=_proveedores(),
                           marcas=_distintos(Repuesto.marca_proveedor))


@bp.route("/markups/<int:mid>/editar", methods=["POST"])
def markup_editar(mid):
    regla = db.get_or_404(ConfigMarkup, mid)
    markup = numero_ar(request.form.get("markup"))
    if not markup or markup < 1:
        flash("El markup tiene que ser 1 o más (1,4 = 40 %).", "error")
    else:
        regla.markup = markup
        db.session.commit()
        flash("Regla guardada. Tocá «Recalcular precios» para aplicarla.", "ok")
    return redirect(url_for(".markups"))


@bp.route("/markups/<int:mid>/eliminar", methods=["POST"])
def markup_eliminar(mid):
    db.session.delete(db.get_or_404(ConfigMarkup, mid))
    db.session.commit()
    flash("Regla eliminada.", "ok")
    return redirect(url_for(".markups"))


@bp.route("/markups/recalcular", methods=["POST"])
def recalcular():
    cambiados = 0
    for r in Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).all():
        antes = r.precio_venta
        if recalcular_precio_venta(r) != antes:
            cambiados += 1
    db.session.commit()
    flash(f"Precios recalculados: {cambiados} repuesto{'s' if cambiados != 1 else ''} cambiaron de precio.", "ok")
    return redirect(url_for(".markups"))


# ─────────────────────────────── Movimientos e ingresos ─────────────────────


@bp.route("/movimientos")
def movimientos():
    movs = MovimientoStock.query.order_by(MovimientoStock.fecha.desc()).limit(300).all()
    return render_template("stock/movimientos.html", movimientos=movs)


@bp.route("/ingresos")
def ingresos():
    estado = request.args.get("estado", "")
    consulta = IngresoStock.query
    if estado:
        consulta = consulta.filter(IngresoStock.estado == estado)
    lista_ingresos = consulta.order_by(IngresoStock.fecha.desc(), IngresoStock.id.desc()).all()
    return render_template("stock/ingresos.html", ingresos=lista_ingresos, estado=estado)


@bp.route("/ingresos/nuevo", methods=["GET", "POST"])
@bp.route("/ingresos/<int:id>", methods=["GET", "POST"])
def ingreso(id=None):
    ing = db.get_or_404(IngresoStock, id) if id else IngresoStock(fecha=date.today(), estado="Borrador")
    if request.method == "POST":
        if id and not ing.editable:
            flash("El ingreso ya está confirmado: no se puede editar.", "error")
            return redirect(url_for(".ingreso", id=id))
        proveedor = request.form.get("proveedor", "").strip()
        if proveedor not in _proveedores():
            flash("Elegí un proveedor de la lista.", "error")
        else:
            ing.proveedor = proveedor
            ing.nro_factura = _texto("nro_factura")
            ing.notas = _texto("notas")
            try:
                ing.fecha = datetime.strptime(request.form.get("fecha", ""), "%Y-%m-%d").date()
            except ValueError:
                ing.fecha = ing.fecha or date.today()
            if not id:
                db.session.add(ing)
            db.session.commit()
            flash("Ingreso guardado." if id else "Ingreso creado: ahora cargá los repuestos.", "ok")
            return redirect(url_for(".ingreso", id=ing.id))
    repuestos = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).order_by(Repuesto.nombre).all()
    return render_template("stock/ingreso.html", ing=ing, proveedores=_proveedores(), repuestos=repuestos)


def _ingreso_editable(id):
    ing = db.get_or_404(IngresoStock, id)
    if not ing.editable:
        flash("El ingreso ya está confirmado.", "error")
        return None
    return ing


@bp.route("/ingresos/<int:id>/items", methods=["POST"])
def ingreso_item_agregar(id):
    ing = _ingreso_editable(id)
    if ing is None:
        return redirect(url_for(".ingreso", id=id))
    texto_repuesto = request.form.get("repuesto", "").strip()
    codigo = texto_repuesto.split("·")[0].strip()
    repuesto = db.session.get(Repuesto, int(codigo)) if codigo.isdigit() else None
    repuesto = repuesto or buscar_repuesto(texto_repuesto)
    cantidad = numero_ar(request.form.get("cantidad")) or 0
    costo = numero_ar(request.form.get("costo_unitario"))
    if repuesto is None or repuesto.id == Repuesto.ID_VARIOS:
        flash(f"No encontré el repuesto «{texto_repuesto}».", "error")
    elif cantidad <= 0:
        flash("La cantidad tiene que ser mayor a cero.", "error")
    else:
        item = next((i for i in ing.items if i.repuesto_id == repuesto.id), None)
        if item:  # el mismo repuesto cargado dos veces: se suma la cantidad
            item.cantidad += cantidad
            if costo is not None:
                item.costo_unitario = costo
        else:
            db.session.add(IngresoStockItem(ingreso=ing, repuesto=repuesto, cantidad=cantidad,
                                            costo_unitario=costo if costo is not None else repuesto.costo_lista))
        db.session.commit()
    return redirect(url_for(".ingreso", id=id) + "#items")


@bp.route("/ingresos/items/<int:iid>/editar", methods=["POST"])
def ingreso_item_editar(iid):
    item = db.get_or_404(IngresoStockItem, iid)
    if _ingreso_editable(item.ingreso_id) is not None:
        cantidad = numero_ar(request.form.get("cantidad"))
        costo = numero_ar(request.form.get("costo_unitario"))
        if not cantidad or cantidad <= 0:
            flash("La cantidad tiene que ser mayor a cero.", "error")
        else:
            item.cantidad = cantidad
            item.costo_unitario = costo
            db.session.commit()
    return redirect(url_for(".ingreso", id=item.ingreso_id) + "#items")


@bp.route("/ingresos/items/<int:iid>/eliminar", methods=["POST"])
def ingreso_item_eliminar(iid):
    item = db.get_or_404(IngresoStockItem, iid)
    ingreso_id = item.ingreso_id
    if _ingreso_editable(ingreso_id) is not None:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for(".ingreso", id=ingreso_id) + "#items")


@bp.route("/ingresos/<int:id>/confirmar", methods=["POST"])
def ingreso_confirmar(id):
    ing = _ingreso_editable(id)
    if ing is None:
        return redirect(url_for(".ingreso", id=id))
    if not ing.items:
        flash("Cargá al menos un repuesto antes de confirmar.", "error")
    else:
        cambios = sum(1 for i in ing.items
                      if i.costo_unitario and not i.repuesto.costo_manual and i.costo_unitario != i.repuesto.costo_lista)
        confirmar_ingreso(ing)
        db.session.commit()
        aviso = f" Se actualizó el costo de {cambios} repuesto{'s' if cambios != 1 else ''}." if cambios else ""
        flash(f"Ingreso confirmado: entraron {len(ing.items)} repuestos al stock.{aviso}", "ok")
    return redirect(url_for(".ingreso", id=id))


@bp.route("/ingresos/<int:id>/anular", methods=["POST"])
def ingreso_anular(id):
    ing = db.get_or_404(IngresoStock, id)
    try:
        anular_ingreso(ing)
        db.session.commit()
        flash("Ingreso anulado: se descontó del stock lo que había entrado.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for(".ingreso", id=id))


@bp.route("/ingresos/<int:id>/eliminar", methods=["POST"])
def ingreso_eliminar(id):
    ing = db.get_or_404(IngresoStock, id)
    if ing.estado == "Confirmado":
        flash("Un ingreso confirmado no se elimina: primero anulalo.", "error")
        return redirect(url_for(".ingreso", id=id))
    db.session.delete(ing)
    db.session.commit()
    flash("Ingreso eliminado.", "ok")
    return redirect(url_for(".ingresos"))
