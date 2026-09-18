from collections import OrderedDict

from flask import Blueprint, render_template
from flask_login import login_required

from ..models import Venta

bp = Blueprint("ventas", __name__)


@bp.before_request
@login_required
def _requiere_login():
    pass


@bp.route("/")
def lista():
    ventas = Venta.query.order_by(Venta.fecha.desc(), Venta.id.desc()).all()
    por_mes = OrderedDict()
    for v in ventas:
        mes = por_mes.setdefault(v.fecha.strftime("%Y-%m"), {"fecha": v.fecha, "total": 0, "costo": 0, "cant": 0})
        mes["total"] += v.total
        mes["costo"] += v.costo_total
        mes["cant"] += 1
    return render_template("ventas/lista.html", ventas=ventas, por_mes=por_mes)
