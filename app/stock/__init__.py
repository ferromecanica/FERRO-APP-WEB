from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from ..models import IngresoStock, MovimientoStock, Repuesto

bp = Blueprint("stock", __name__)


@bp.before_request
@login_required
def _requiere_login():
    pass


@bp.route("/")
def lista():
    q = request.args.get("q", "").strip()
    consulta = Repuesto.query
    if q:
        like = f"%{q}%"
        consulta = consulta.filter(or_(Repuesto.nombre.ilike(like), Repuesto.nro_parte.ilike(like),
                                       Repuesto.codigo_barras.ilike(like), Repuesto.marca.ilike(like)))
    repuestos = consulta.order_by(Repuesto.nombre).all()
    return render_template("stock/lista.html", repuestos=repuestos, q=q)


@bp.route("/movimientos")
def movimientos():
    movs = MovimientoStock.query.order_by(MovimientoStock.fecha.desc()).limit(200).all()
    return render_template("stock/movimientos.html", movimientos=movs)


@bp.route("/ingresos")
def ingresos():
    ingresos = IngresoStock.query.order_by(IngresoStock.fecha.desc()).all()
    return render_template("stock/ingresos.html", ingresos=ingresos)
