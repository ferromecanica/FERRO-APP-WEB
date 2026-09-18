from datetime import date

from flask import Blueprint, render_template
from flask_login import login_required

from ..models import Turno

bp = Blueprint("turnos", __name__)


@bp.before_request
@login_required
def _requiere_login():
    pass


@bp.route("/")
def lista():
    proximos = Turno.query.filter(Turno.fecha >= date.today()).order_by(Turno.fecha, Turno.hora).all()
    return render_template("turnos/lista.html", turnos=proximos)
