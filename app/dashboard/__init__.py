from datetime import date

from flask import Blueprint, render_template
from flask_login import login_required

from ..models import OrdenTrabajo, Repuesto, Turno, Venta

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    ventas_mes = Venta.query.filter(Venta.fecha >= inicio_mes).all()
    ots_abiertas = OrdenTrabajo.query.filter(OrdenTrabajo.estado.notin_(["Terminado", "Entregado"])) \
        .order_by(OrdenTrabajo.fecha_ingreso).all()
    turnos = Turno.query.filter(Turno.fecha >= hoy, Turno.estado != "Cancelado") \
        .order_by(Turno.fecha, Turno.hora).limit(6).all()
    bajo_stock = [r for r in Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).all() if r.bajo_stock]

    facturado = sum(v.total for v in ventas_mes)
    ganancia = sum(v.ganancia for v in ventas_mes)
    return render_template(
        "dashboard/index.html",
        facturado=facturado,
        ganancia=ganancia,
        cant_ventas=len(ventas_mes),
        ots_abiertas=ots_abiertas,
        turnos=turnos,
        bajo_stock=bajo_stock[:8],
        cant_bajo_stock=len(bajo_stock),
    )
