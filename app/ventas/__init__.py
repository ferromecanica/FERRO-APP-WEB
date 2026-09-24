"""Ventas: las que salen de una OT al cerrarla y las de mostrador.

La venta de mostrador se arma en la sesión del navegador (como el cotizador) y
recién al cobrar se guarda y se descuenta el stock: así no quedan ventas a medio
hacer en la base.
"""
from collections import OrderedDict
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import login_required

from ..extensions import db
from ..models import Cliente, CondicionPago, Repuesto, Venta
from ..services import cobros, contable
from ..services.stock import anular_venta, buscar_repuesto, vender_en_mostrador
from ..validaciones import numero_ar

bp = Blueprint("ventas", __name__)


@bp.before_request
@login_required
def _requiere_login():
    pass


@bp.route("/")
def lista():
    q = request.args.get("q", "").strip()
    consulta = Venta.query.outerjoin(Cliente)
    if q:
        like = f"%{q}%"
        filtros = [Cliente.nombre.ilike(like), Venta.metodo_pago.ilike(like)]
        if q.isdigit():
            filtros += [Venta.id == int(q), Venta.ot_id == int(q)]
        consulta = consulta.filter(db.or_(*filtros))
    ventas = consulta.order_by(Venta.fecha.desc(), Venta.id.desc()).all()

    meses = OrderedDict()
    for v in ventas:
        clave = v.fecha.strftime("%Y-%m")
        mes = meses.setdefault(clave, {"clave": clave, "fecha": v.fecha.replace(day=1),
                                       "total": 0, "costo": 0, "ventas": []})
        mes["total"] += v.cobrado
        mes["costo"] += v.costo_total
        mes["ventas"].append(v)
    # El mes en curso viene abierto; los anteriores, plegados con su resumen.
    return render_template("ventas/lista.html", meses=meses.values(), cantidad=len(ventas), q=q,
                           mes_actual=date.today().strftime("%Y-%m"))


@bp.route("/<int:id>")
def detalle(id):
    venta = db.get_or_404(Venta, id)
    return render_template("ventas/detalle.html", v=venta, hoy=date.today())


@bp.route("/<int:id>/anular", methods=["POST"])
def anular(id):
    venta = db.get_or_404(Venta, id)
    try:
        anular_venta(venta)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for(".detalle", id=id))
    contable.borrar_venta(venta)
    db.session.delete(venta)
    db.session.commit()
    flash(f"Venta {id} anulada: los repuestos volvieron al stock.", "ok")
    return redirect(url_for(".lista"))


# ─────────────────────────────── Mostrador ──────────────────────────────────


def _mostrador():
    venta = session.get("mostrador")
    if not venta:
        venta = {"items": [], "proximo_id": 1, "cliente_id": None, "condicion_id": None}
        session["mostrador"] = venta
    return venta


def _guardar(venta):
    session["mostrador"] = venta
    session.modified = True


def _totales(venta):
    total = sum(i["cantidad"] * i["precio"] for i in venta["items"])
    costo = sum(i["cantidad"] * i["costo"] for i in venta["items"])
    return {"total": total, "costo": costo, "ganancia": total - costo}


@bp.route("/mostrador")
def mostrador():
    venta = _mostrador()
    return render_template(
        "ventas/mostrador.html", venta=venta, t=_totales(venta),
        condiciones=CondicionPago.query.filter_by(activa=True).order_by(CondicionPago.orden).all(),
        repuestos=Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).order_by(Repuesto.nombre).all(),
        clientes=Cliente.query.order_by(db.func.lower(Cliente.nombre)).all(),
        hoy=date.today(),
    )


@bp.route("/mostrador/items", methods=["POST"])
def item_agregar():
    venta = _mostrador()
    cantidad = numero_ar(request.form.get("cantidad"))
    cantidad = 1 if cantidad is None else cantidad
    if cantidad <= 0:
        flash("La cantidad tiene que ser mayor a cero.", "error")
        return redirect(url_for(".mostrador"))

    if request.form.get("tipo") == "stock":
        texto = request.form.get("repuesto", "").strip()
        codigo = texto.split("·")[0].strip()
        repuesto = db.session.get(Repuesto, int(codigo)) if codigo.isdigit() else None
        repuesto = repuesto or buscar_repuesto(texto)
        if repuesto is None or repuesto.id == Repuesto.ID_VARIOS:
            flash(f"No encontré el repuesto «{texto}».", "error")
            return redirect(url_for(".mostrador"))
        if repuesto.controla_stock and cantidad > (repuesto.stock_actual or 0):
            flash(f"Ojo: hay {repuesto.stock_actual or 0:g} de {repuesto.nombre} y estás vendiendo {cantidad:g}.", "info")
        item = {"id": venta["proximo_id"], "repuesto_id": repuesto.id, "descripcion": repuesto.nombre,
                "cantidad": cantidad, "precio": repuesto.precio_venta or 0, "costo": repuesto.precio_costo or 0}
    else:
        descripcion = request.form.get("descripcion", "").strip()
        precio = numero_ar(request.form.get("precio"))
        if not descripcion or precio is None:
            flash("Para un ítem a mano poné descripción y precio.", "error")
            return redirect(url_for(".mostrador"))
        item = {"id": venta["proximo_id"], "repuesto_id": None, "descripcion": descripcion,
                "cantidad": cantidad, "precio": precio, "costo": numero_ar(request.form.get("costo")) or 0}

    venta["items"].append(item)
    venta["proximo_id"] += 1
    _guardar(venta)
    return redirect(url_for(".mostrador") + "#items")


@bp.route("/mostrador/items/<int:iid>/editar", methods=["POST"])
def item_editar(iid):
    venta = _mostrador()
    for item in venta["items"]:
        if item["id"] == iid:
            cantidad = numero_ar(request.form.get("cantidad"))
            precio = numero_ar(request.form.get("precio"))
            if not cantidad or cantidad <= 0 or precio is None:
                flash("Revisá cantidad y precio.", "error")
            else:
                item.update(cantidad=cantidad, precio=precio, costo=numero_ar(request.form.get("costo")) or 0,
                            descripcion=request.form.get("descripcion", item["descripcion"]).strip() or item["descripcion"])
                _guardar(venta)
            break
    return redirect(url_for(".mostrador") + "#items")


@bp.route("/mostrador/items/<int:iid>/eliminar", methods=["POST"])
def item_eliminar(iid):
    venta = _mostrador()
    venta["items"] = [i for i in venta["items"] if i["id"] != iid]
    _guardar(venta)
    return redirect(url_for(".mostrador") + "#items")


@bp.route("/mostrador/limpiar", methods=["POST"])
def limpiar():
    session.pop("mostrador", None)
    flash("Mostrador vacío.", "ok")
    return redirect(url_for(".mostrador"))


@bp.route("/mostrador/cobrar", methods=["POST"])
def cobrar():
    """Guarda la venta y descuenta el stock de una sola vez."""
    borrador = _mostrador()
    if not borrador["items"]:
        flash("Cargá lo que estás vendiendo.", "error")
        return redirect(url_for(".mostrador"))

    # Sin importe escrito se cobra el total de lo que se lleva, que es lo que dice la pantalla
    partes, errores = cobros.leer_del_formulario(request.form, sugerido=_totales(borrador)['total'])
    if errores:
        for e in errores:
            flash(e, "error")
        return redirect(url_for(".mostrador"))
    try:
        fecha = datetime.strptime(request.form.get("fecha", ""), "%Y-%m-%d").date()
    except ValueError:
        fecha = date.today()
    venta = Venta(
        fecha=fecha,
        cliente=db.session.get(Cliente, request.form.get("cliente_id", type=int) or 0),
        tipo_comprobante="X",
    )
    cobros.anotar(venta, partes, fecha)
    db.session.add(venta)
    db.session.flush()
    for item in borrador["items"]:
        vender_en_mostrador(
            venta, db.session.get(Repuesto, item["repuesto_id"]) if item["repuesto_id"] else None,
            item["cantidad"], precio_unitario=item["precio"], costo_unitario=item["costo"],
            descripcion=item["descripcion"],
        )
    contable.registrar_venta(venta)
    db.session.commit()
    session.pop("mostrador", None)
    flash(f"Venta {venta.id} registrada. Percibimos ${venta.cobrado:,.0f}".replace(",", ".") + ".", "ok")
    return redirect(url_for(".detalle", id=venta.id))
