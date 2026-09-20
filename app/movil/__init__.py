"""Vista para el celular (pensada para Iván en el taller): OT abiertas, fotos, tareas y horas."""
from datetime import date, timedelta

from flask import Blueprint, render_template, request
from flask_login import login_required

from ..extensions import db
from ..models import ESTADOS_OT_ABIERTA, OrdenTrabajo, RegistroHoras, Vehiculo

bp = Blueprint("movil", __name__)


@bp.before_request
@login_required
def _requiere_login():
    pass


@bp.route("/")
def inicio():
    q = request.args.get("q", "").strip().upper().replace(" ", "")
    consulta = OrdenTrabajo.query.join(Vehiculo)
    if q:
        consulta = consulta.filter(Vehiculo.patente.contains(q))
    abiertas = consulta.filter(OrdenTrabajo.estado.in_(ESTADOS_OT_ABIERTA)).order_by(OrdenTrabajo.id.desc()).all()
    terminadas = consulta.filter(OrdenTrabajo.estado == "Finalizada")
    if not q:  # sin buscar, solo las de la última semana; buscando, todas las de esa patente
        terminadas = terminadas.filter(OrdenTrabajo.fecha_fin >= date.today() - timedelta(days=7))
    recientes = terminadas.order_by(OrdenTrabajo.fecha_fin.desc(), OrdenTrabajo.id.desc()).limit(30).all()
    return render_template("movil/inicio.html", abiertas=abiertas, recientes=recientes, q=q)


@bp.route("/ot/<int:id>")
def ot(id):
    orden = db.get_or_404(OrdenTrabajo, id)
    usados = [m for (m,) in db.session.query(RegistroHoras.mecanico).distinct() if m]
    return render_template("movil/ot.html", ot=orden, mecanicos=sorted(set(usados) | {"Iván", "Lucio"}))
