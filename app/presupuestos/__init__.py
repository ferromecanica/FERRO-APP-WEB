"""Presupuestos: trabajos a realizar, repuestos, mano de obra y PDF."""
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    ESTADOS_PRESUPUESTO,
    Cliente,
    ConfigTaller,
    Presupuesto,
    PresupuestoItem,
    PresupuestoTrabajo,
    Repuesto,
    Vehiculo,
)
from ..services import reporte
from ..services.stock import buscar_repuesto
from ..validaciones import numero_ar

bp = Blueprint("presupuestos", __name__)


@bp.before_request
@login_required
def _requiere_login():
    pass


def _editable(id):
    p = db.get_or_404(Presupuesto, id)
    if not p.editable:
        flash(f"El presupuesto está {p.estado.lower()}: no se puede modificar.", "error")
        return None
    return p


def _volver(id, seccion=None):
    return redirect(url_for(".ficha", id=id) + (f"#{seccion}" if seccion else ""))


def _datos_comunes():
    clientes = Cliente.query.order_by(db.func.lower(Cliente.nombre)).all()
    return {
        "clientes": clientes,
        "vehiculos_por_cliente": {c.id: [{"id": v.id, "texto": f"{v.patente} · {v.descripcion}".strip(" ·")}
                                         for v in c.vehiculos] for c in clientes},
        "repuestos": Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).order_by(Repuesto.nombre).all(),
    }


@bp.route("/")
def lista():
    estado = request.args.get("estado", "")
    q = request.args.get("q", "").strip()
    consulta = Presupuesto.query.join(Cliente).outerjoin(Vehiculo, Presupuesto.vehiculo_id == Vehiculo.id)
    if estado:
        consulta = consulta.filter(Presupuesto.estado == estado)
    if q:
        like = f"%{q}%"
        filtros = [Cliente.nombre.ilike(like), Vehiculo.patente.ilike(like)]
        if q.isdigit():
            filtros.append(Presupuesto.id == int(q))
        consulta = consulta.filter(or_(*filtros))
    presupuestos = consulta.order_by(Presupuesto.id.desc()).all()
    return render_template("presupuestos/lista.html", presupuestos=presupuestos, estado=estado, q=q,
                           estados=ESTADOS_PRESUPUESTO)


@bp.route("/nuevo", methods=["GET", "POST"])
@bp.route("/<int:id>/cabecera", methods=["POST"])
def form(id=None):
    p = db.get_or_404(Presupuesto, id) if id else Presupuesto(fecha=date.today(), estado="Borrador",
                                                              mostrar_precios_detalle=True)
    if request.method == "POST":
        if id and not p.editable:
            flash("El presupuesto ya no se puede modificar.", "error")
            return _volver(id)
        cliente = db.session.get(Cliente, request.form.get("cliente_id", type=int) or 0)
        vehiculo = db.session.get(Vehiculo, request.form.get("vehiculo_id", type=int) or 0)
        if cliente is None:
            flash("Elegí el cliente.", "error")
        else:
            p.cliente = cliente
            p.vehiculo = vehiculo if vehiculo and vehiculo.cliente_id == cliente.id else None
            p.mostrar_precios_detalle = bool(request.form.get("mostrar_precios_detalle"))
            try:
                p.fecha = datetime.strptime(request.form.get("fecha", ""), "%Y-%m-%d").date()
            except ValueError:
                p.fecha = p.fecha or date.today()
            if not id:
                p.id = Presupuesto.proximo_numero()
                p.valor_hora = ConfigTaller.get().valor_hora or 0
                db.session.add(p)
            db.session.commit()
            flash("Presupuesto guardado." if id else f"Presupuesto #{p.id} creado: cargá los trabajos y repuestos.", "ok")
            return _volver(p.id)
    return render_template("presupuestos/form.html", p=p, **_datos_comunes())


@bp.route("/<int:id>")
def ficha(id):
    p = db.get_or_404(Presupuesto, id)
    return render_template("presupuestos/ficha.html", p=p, estados=ESTADOS_PRESUPUESTO,
                           reportes_configurados=reporte.configurado(), **_datos_comunes())


# ───────────────────────────── Trabajos y repuestos ─────────────────────────


@bp.route("/<int:id>/trabajos", methods=["POST"])
def trabajo_agregar(id):
    p = _editable(id)
    if p is None:
        return _volver(id)
    texto = request.form.get("descripcion", "").strip()
    if texto:
        db.session.add(PresupuestoTrabajo(presupuesto=p, descripcion=texto))
        db.session.commit()
    return _volver(id, "trabajos")


@bp.route("/trabajos/<int:tid>/eliminar", methods=["POST"])
def trabajo_eliminar(tid):
    trabajo = db.get_or_404(PresupuestoTrabajo, tid)
    pid = trabajo.presupuesto_id
    if _editable(pid) is not None:
        db.session.delete(trabajo)
        db.session.commit()
    return _volver(pid, "trabajos")


@bp.route("/<int:id>/items", methods=["POST"])
def item_agregar(id):
    p = _editable(id)
    if p is None:
        return _volver(id)
    cantidad = numero_ar(request.form.get("cantidad"))
    cantidad = 1 if cantidad is None else cantidad
    if cantidad <= 0:
        flash("La cantidad tiene que ser mayor a cero.", "error")
        return _volver(id, "items")
    if request.form.get("tipo") == "stock":
        texto = request.form.get("repuesto", "").strip()
        codigo = texto.split("·")[0].strip()
        repuesto = db.session.get(Repuesto, int(codigo)) if codigo.isdigit() else None
        repuesto = repuesto or buscar_repuesto(texto)
        if repuesto is None or repuesto.id == Repuesto.ID_VARIOS:
            flash(f"No encontré el repuesto «{texto}».", "error")
            return _volver(id, "items")
        db.session.add(PresupuestoItem(presupuesto=p, repuesto=repuesto, descripcion=repuesto.nombre,
                                       cantidad=cantidad, precio_unitario=repuesto.precio_venta or 0,
                                       costo_unitario=repuesto.precio_costo or 0))
    else:
        descripcion = request.form.get("descripcion", "").strip()
        precio = numero_ar(request.form.get("precio"))
        if not descripcion or precio is None:
            flash("Para un ítem manual poné descripción y precio.", "error")
            return _volver(id, "items")
        db.session.add(PresupuestoItem(presupuesto=p, descripcion=descripcion, cantidad=cantidad,
                                       precio_unitario=precio, costo_unitario=numero_ar(request.form.get("costo")) or 0))
    db.session.commit()
    return _volver(id, "items")


@bp.route("/items/<int:iid>/editar", methods=["POST"])
def item_editar(iid):
    item = db.get_or_404(PresupuestoItem, iid)
    pid = item.presupuesto_id
    if _editable(pid) is not None:
        cantidad = numero_ar(request.form.get("cantidad"))
        precio = numero_ar(request.form.get("precio"))
        if not cantidad or cantidad <= 0 or precio is None:
            flash("Revisá cantidad y precio.", "error")
        else:
            item.cantidad, item.precio_unitario = cantidad, precio
            item.costo_unitario = numero_ar(request.form.get("costo")) or 0
            item.descripcion = request.form.get("descripcion", item.descripcion).strip() or item.descripcion
            db.session.commit()
    return _volver(pid, "items")


@bp.route("/items/<int:iid>/eliminar", methods=["POST"])
def item_eliminar(iid):
    item = db.get_or_404(PresupuestoItem, iid)
    pid = item.presupuesto_id
    if _editable(pid) is not None:
        db.session.delete(item)
        db.session.commit()
    return _volver(pid, "items")


@bp.route("/<int:id>/mano-obra", methods=["POST"])
def mano_obra(id):
    p = _editable(id)
    if p is None:
        return _volver(id)
    p.modo_mano_obra = "Por monto" if request.form.get("modo") == "Por monto" else "Por horas"
    p.horas_mano_obra = numero_ar(request.form.get("horas")) or 0
    p.monto_fijo_mo = numero_ar(request.form.get("monto")) or 0
    p.valor_hora = numero_ar(request.form.get("valor_hora")) or p.valor_hora or (ConfigTaller.get().valor_hora or 0)
    db.session.commit()
    return _volver(id, "mano-obra")


# ──────────────────────────────── Estado y PDF ──────────────────────────────


@bp.route("/<int:id>/estado", methods=["POST"])
def estado(id):
    p = db.get_or_404(Presupuesto, id)
    nuevo = request.form.get("estado")
    if nuevo in ESTADOS_PRESUPUESTO:
        p.estado = nuevo
        db.session.commit()
        flash(f"Presupuesto {nuevo.lower()}.", "ok")
    return _volver(id)


@bp.route("/<int:id>/pdf", methods=["POST"])
def pdf(id):
    p = db.get_or_404(Presupuesto, id)
    try:
        reporte.generar_pdf_presupuesto(p)
        db.session.commit()
        flash("PDF generado en Drive.", "ok")
    except reporte.ErrorReporte as e:
        db.session.rollback()
        flash(str(e), "error")
    return _volver(id)


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    p = db.get_or_404(Presupuesto, id)
    db.session.delete(p)
    db.session.commit()
    flash(f"Presupuesto #{id} eliminado.", "ok")
    return redirect(url_for(".lista"))
