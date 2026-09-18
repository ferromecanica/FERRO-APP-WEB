from flask import Blueprint, render_template, request
from flask_login import login_required

from ..extensions import db
from ..models import ESTADOS_OT, OrdenTrabajo

bp = Blueprint("ot", __name__)


@bp.before_request
@login_required
def _requiere_login():
    pass


@bp.route("/")
def lista():
    estado = request.args.get("estado")
    consulta = OrdenTrabajo.query
    if estado:
        consulta = consulta.filter_by(estado=estado)
    ordenes = consulta.order_by(OrdenTrabajo.id.desc()).all()
    return render_template("ot/lista.html", ordenes=ordenes, estados=ESTADOS_OT, estado=estado)


@bp.route("/<int:id>")
def detalle(id):
    ot = db.get_or_404(OrdenTrabajo, id)
    return render_template("ot/detalle.html", ot=ot)
