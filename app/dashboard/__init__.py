from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..extensions import db
from ..models import ConfigTaller, OrdenTrabajo, Repuesto, Turno, Venta
from ..validaciones import numero_ar

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


@bp.route("/configuracion", methods=["GET", "POST"])
@login_required
def configuracion():
    cfg = ConfigTaller.get()
    if request.method == "POST":
        valor = numero_ar(request.form.get("valor_hora"))
        if valor is None or valor < 0:
            flash("Poné un valor de hora válido.", "error")
        else:
            cfg.valor_hora = valor
            for campo in ("razon_social", "cuit", "direccion", "telefono"):
                setattr(cfg, campo, request.form.get(campo, "").strip() or None)
            db.session.commit()
            flash("Configuración guardada.", "ok")
            return redirect(url_for(".configuracion"))
    return render_template("dashboard/configuracion.html", cfg=cfg)
