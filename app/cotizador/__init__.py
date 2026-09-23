"""Cotizador: sacar rápido cuánto vale un trabajo, sin guardar nada.

Vive en la sesión del navegador (cada uno tiene la suya). Si el número cierra, se
pasa a un presupuesto (ahí sí se guarda y se genera el PDF).
"""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import login_required

from ..extensions import db
from ..models import (
    Cliente,
    CondicionPago,
    ConfigTaller,
    Presupuesto,
    PresupuestoItem,
    PresupuestoTrabajo,
    Repuesto,
    Vehiculo,
)
from ..services.stock import buscar_repuesto
from ..validaciones import numero_ar

bp = Blueprint("cotizador", __name__)


@bp.before_request
@login_required
def _requiere_login():
    pass


def _cotizacion():
    """Lo que hay cargado ahora (se guarda en la sesión del navegador)."""
    coti = session.get("cotizacion")
    if not coti:
        coti = {"items": [], "modo_mo": "horas", "horas": 0, "monto_mo": 0, "proximo_id": 1}
        session["cotizacion"] = coti
    return coti


def _guardar(coti):
    session["cotizacion"] = coti
    session.modified = True


def _totales(coti):
    valor_hora = ConfigTaller.get().valor_hora or 0
    repuestos = sum(i["cantidad"] * i["precio"] for i in coti["items"])
    costo = sum(i["cantidad"] * i["costo"] for i in coti["items"])
    mano_obra = (coti["horas"] * valor_hora) if coti["modo_mo"] == "horas" else coti["monto_mo"]
    total = repuestos + mano_obra
    return {
        "valor_hora": valor_hora, "repuestos": repuestos, "costo": costo, "mano_obra": mano_obra,
        "total": total, "ganancia": total - costo,
        "margen": (total - costo) / total * 100 if total else 0,
    }


def _formas_de_pago(total):
    """Cuánto sale el trabajo según cómo lo pague, para que al taller le entre el total.

    El cotizador dice lo que queremos percibir; la tarjeta se queda con lo suyo,
    así que el precio que se le pasa al cliente cambia con la forma de pago.
    """
    if not total:
        return []
    condiciones = CondicionPago.query.filter_by(activa=True).order_by(
        CondicionPago.orden, CondicionPago.id).all()
    formas = []
    for c in condiciones:
        cobra = c.bruto(total)
        formas.append({"nombre": c.nombre, "recargo": c.recargo_usado, "cobra": cobra,
                       "entra": c.neto(cobra), "dias": c.dias_habiles})
    return formas


@bp.route("/")
def inicio():
    coti = _cotizacion()
    repuestos = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).order_by(Repuesto.nombre).all()
    clientes = Cliente.query.order_by(db.func.lower(Cliente.nombre)).all()
    totales = _totales(coti)
    return render_template("cotizador/inicio.html", coti=coti, t=totales, repuestos=repuestos,
                           clientes=clientes, formas=_formas_de_pago(totales["total"]),
                           vehiculos_por_cliente={c.id: [{"id": v.id, "texto": f"{v.patente} · {v.descripcion}".strip(" ·")}
                                                         for v in c.vehiculos] for c in clientes})


@bp.route("/items", methods=["POST"])
def item_agregar():
    coti = _cotizacion()
    cantidad = numero_ar(request.form.get("cantidad")) or 1
    if cantidad <= 0:
        flash("La cantidad tiene que ser mayor a cero.", "error")
        return redirect(url_for(".inicio"))

    if request.form.get("tipo") == "stock":
        texto = request.form.get("repuesto", "").strip()
        codigo = texto.split("·")[0].strip()
        repuesto = db.session.get(Repuesto, int(codigo)) if codigo.isdigit() else None
        repuesto = repuesto or buscar_repuesto(texto)
        if repuesto is None or repuesto.id == Repuesto.ID_VARIOS:
            flash(f"No encontré el repuesto «{texto}».", "error")
            return redirect(url_for(".inicio"))
        item = {"id": coti["proximo_id"], "repuesto_id": repuesto.id, "descripcion": repuesto.nombre,
                "cantidad": cantidad, "precio": repuesto.precio_venta or 0, "costo": repuesto.precio_costo or 0}
    else:
        descripcion = request.form.get("descripcion", "").strip()
        precio = numero_ar(request.form.get("precio"))
        if not descripcion or precio is None:
            flash("Para un ítem manual poné descripción y precio.", "error")
            return redirect(url_for(".inicio"))
        item = {"id": coti["proximo_id"], "repuesto_id": None, "descripcion": descripcion,
                "cantidad": cantidad, "precio": precio, "costo": numero_ar(request.form.get("costo")) or 0}
    coti["items"].append(item)
    coti["proximo_id"] += 1
    _guardar(coti)
    return redirect(url_for(".inicio") + "#items")


@bp.route("/items/<int:iid>/editar", methods=["POST"])
def item_editar(iid):
    coti = _cotizacion()
    for item in coti["items"]:
        if item["id"] == iid:
            cantidad = numero_ar(request.form.get("cantidad"))
            precio = numero_ar(request.form.get("precio"))
            if not cantidad or cantidad <= 0 or precio is None:
                flash("Revisá cantidad y precio.", "error")
            else:
                item.update(cantidad=cantidad, precio=precio, costo=numero_ar(request.form.get("costo")) or 0,
                            descripcion=request.form.get("descripcion", item["descripcion"]).strip() or item["descripcion"])
                _guardar(coti)
            break
    return redirect(url_for(".inicio") + "#items")


@bp.route("/items/<int:iid>/eliminar", methods=["POST"])
def item_eliminar(iid):
    coti = _cotizacion()
    coti["items"] = [i for i in coti["items"] if i["id"] != iid]
    _guardar(coti)
    return redirect(url_for(".inicio") + "#items")


@bp.route("/mano-obra", methods=["POST"])
def mano_obra():
    coti = _cotizacion()
    coti["modo_mo"] = "monto" if request.form.get("modo_mo") == "monto" else "horas"
    coti["horas"] = numero_ar(request.form.get("horas")) or 0
    coti["monto_mo"] = numero_ar(request.form.get("monto_mo")) or 0
    _guardar(coti)
    return redirect(url_for(".inicio") + "#mano-obra")


@bp.route("/pasar-a-presupuesto", methods=["POST"])
def pasar_a_presupuesto():
    """Guarda lo cotizado como presupuesto y vacía el cotizador."""
    coti = _cotizacion()
    cliente = db.session.get(Cliente, request.form.get("cliente_id", type=int) or 0)
    if cliente is None:
        flash("Elegí el cliente para pasar la cotización a presupuesto.", "error")
        return redirect(url_for(".inicio"))
    if not coti["items"] and not _totales(coti)["mano_obra"]:
        flash("La cotización está vacía.", "error")
        return redirect(url_for(".inicio"))
    trabajos = [t.strip(" -•\t") for t in request.form.get("trabajos", "").splitlines()]
    trabajos = [t for t in trabajos if t]
    if not trabajos:
        flash("Escribí los trabajos a realizar: van en el PDF del presupuesto.", "error")
        return redirect(url_for(".inicio") + "#pasar")

    vehiculo = db.session.get(Vehiculo, request.form.get("vehiculo_id", type=int) or 0)
    t = _totales(coti)
    p = Presupuesto(
        id=Presupuesto.proximo_numero(), fecha=date.today(), estado="Borrador", cliente=cliente,
        vehiculo=vehiculo if vehiculo and vehiculo.cliente_id == cliente.id else None,
        mostrar_precios_detalle=True, valor_hora=t["valor_hora"],
        modo_mano_obra="Por monto" if coti["modo_mo"] == "monto" else "Por horas",
        horas_mano_obra=coti["horas"], monto_fijo_mo=coti["monto_mo"],
    )
    db.session.add(p)
    for texto in trabajos:
        db.session.add(PresupuestoTrabajo(presupuesto=p, descripcion=texto))
    for i in coti["items"]:
        db.session.add(PresupuestoItem(presupuesto=p, repuesto_id=i["repuesto_id"], descripcion=i["descripcion"],
                                       cantidad=i["cantidad"], precio_unitario=i["precio"], costo_unitario=i["costo"]))
    db.session.commit()
    session.pop("cotizacion", None)
    flash(f"Presupuesto #{p.id} creado con lo cotizado.", "ok")
    return redirect(url_for("presupuestos.ficha", id=p.id))


@bp.route("/limpiar", methods=["POST"])
def limpiar():
    session.pop("cotizacion", None)
    flash("Cotización vaciada.", "ok")
    return redirect(url_for(".inicio"))
