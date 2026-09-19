from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func, or_

from ..extensions import db
from ..models import (
    Categoria,
    ConfigMarkup,
    ConsumoOT,
    IngresoStockItem,
    MovimientoStock,
    PresupuestoItem,
    Repuesto,
    Subcategoria,
    VentaItem,
)
from ..services.stock import recalcular_precio_venta, regla_markup, registrar_movimiento
from ..validaciones import numero_ar

bp = Blueprint("stock", __name__)

CAMPOS_TEXTO = ["nombre", "marca", "nro_parte", "codigo_barras", "proveedor", "cod_proveedor", "marca_proveedor",
                "comp_marca", "comp_modelo", "comp_motor", "detalle"]


@bp.before_request
@login_required
def _requiere_login():
    pass


def _texto(campo):
    return request.form.get(campo, "").strip() or None


def _distintos(columna):
    return sorted({v for (v,) in db.session.query(columna).distinct() if v}, key=str.lower)


def _categoria(nombre):
    """Busca la categoría por nombre o la crea (se escriben en mayúsculas, como en AppSheet)."""
    nombre = (nombre or "").strip().upper()
    if not nombre:
        return None
    cat = Categoria.query.filter(func.upper(Categoria.nombre) == nombre).first()
    if cat is None:
        cat = Categoria(nombre=nombre)
        db.session.add(cat)
    return cat


def _subcategoria(nombre, categoria):
    nombre = (nombre or "").strip().upper()
    if not nombre or categoria is None:
        return None
    sub = None
    if categoria.id:
        sub = Subcategoria.query.filter(Subcategoria.categoria_id == categoria.id,
                                        func.upper(Subcategoria.nombre) == nombre).first()
    if sub is None:
        sub = Subcategoria(nombre=nombre, categoria=categoria)
        db.session.add(sub)
    return sub


# ─────────────────────────────────── Repuestos ──────────────────────────────


@bp.route("/")
def lista():
    q = request.args.get("q", "").strip()
    categoria_id = request.args.get("categoria", type=int)
    filtro = request.args.get("filtro", "")
    consulta = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS)
    if q:
        for palabra in q.split():  # todas las palabras tienen que aparecer en algún campo
            like = f"%{palabra}%"
            filtro_id = [Repuesto.id == int(palabra)] if palabra.isdigit() else []
            consulta = consulta.filter(or_(
                Repuesto.nombre.ilike(like), Repuesto.nro_parte.ilike(like), Repuesto.codigo_barras.ilike(like),
                Repuesto.marca.ilike(like), Repuesto.detalle.ilike(like), Repuesto.comp_marca.ilike(like),
                Repuesto.comp_modelo.ilike(like), Repuesto.comp_motor.ilike(like), Repuesto.cod_proveedor.ilike(like),
                *filtro_id))
    if categoria_id:
        consulta = consulta.filter(Repuesto.categoria_id == categoria_id)
    if filtro == "sin_stock":
        consulta = consulta.filter(Repuesto.stock_actual <= 0)
    elif filtro == "con_stock":
        consulta = consulta.filter(Repuesto.stock_actual > 0)
    elif filtro == "bajo":
        consulta = consulta.filter(Repuesto.stock_actual <= func.coalesce(Repuesto.stock_minimo, 0))
    repuestos = consulta.order_by(Repuesto.id).all()
    plantilla = "stock/_tabla.html" if request.headers.get("HX-Request") else "stock/lista.html"
    return render_template(plantilla, repuestos=repuestos, q=q, categorias=Categoria.query.order_by(Categoria.nombre).all(),
                           categoria_id=categoria_id, filtro=filtro)


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
        repuesto.categoria = _categoria(request.form.get("categoria"))
        repuesto.subcategoria = _subcategoria(request.form.get("subcategoria"), repuesto.categoria)
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
        categorias=Categoria.query.order_by(Categoria.nombre).all(),
        subcategorias=Subcategoria.query.order_by(Subcategoria.nombre).all(),
        proveedores=_distintos(Repuesto.proveedor), marcas=_distintos(Repuesto.marca),
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
    db.session.delete(repuesto)
    db.session.commit()
    flash(f"Repuesto #{id} eliminado.", "ok")
    return redirect(url_for(".lista"))


# ──────────────────────────────────── Markups ───────────────────────────────


@bp.route("/markups", methods=["GET", "POST"])
def markups():
    if request.method == "POST":
        proveedor = request.form.get("proveedor", "").strip()
        marca = request.form.get("marca_envase", "").strip() or None
        markup = numero_ar(request.form.get("markup"))
        if not proveedor or not markup or markup < 1:
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
    return render_template("stock/markups.html", reglas=reglas, uso=uso, proveedores=_distintos(Repuesto.proveedor),
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
    from ..models import IngresoStock
    ingresos = IngresoStock.query.order_by(IngresoStock.fecha.desc()).all()
    return render_template("stock/ingresos.html", ingresos=ingresos)
