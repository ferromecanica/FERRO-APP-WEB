from flask import Blueprint, render_template
from flask_login import login_required

from ..models import Presupuesto

bp = Blueprint("presupuestos", __name__)


@bp.before_request
@login_required
def _requiere_login():
    pass


@bp.route("/")
def lista():
    presupuestos = Presupuesto.query.order_by(Presupuesto.id.desc()).all()
    return render_template("presupuestos/lista.html", presupuestos=presupuestos)
