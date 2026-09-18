from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import Cliente, Vehiculo

bp = Blueprint("clientes", __name__)

CONDICIONES_IVA = ["Consumidor Final", "Responsable Inscripto", "Monotributista", "Exento"]
CAMPOS_CLIENTE = ["nombre", "telefono", "email", "direccion", "cuit", "condicion_iva", "notas"]
CAMPOS_VEHICULO = ["marca", "modelo", "motor", "traccion", "color", "vin", "ecu_marca", "ecu_modelo"]


def _texto(campo):
    return request.form.get(campo, "").strip() or None


def _entero(campo):
    valor = request.form.get(campo, "").replace(".", "").strip()
    return int(valor) if valor.isdigit() else None


@bp.before_request
@login_required
def _requiere_login():
    pass


@bp.route("/")
def lista():
    q = request.args.get("q", "").strip()
    consulta = Cliente.query
    if q:
        like = f"%{q}%"
        consulta = consulta.outerjoin(Vehiculo).filter(
            or_(Cliente.nombre.ilike(like), Cliente.telefono.ilike(like), Vehiculo.patente.ilike(like))
        ).distinct()
    clientes = consulta.order_by(Cliente.nombre).all()
    plantilla = "clientes/_tabla.html" if request.headers.get("HX-Request") else "clientes/lista.html"
    return render_template(plantilla, clientes=clientes, q=q)


@bp.route("/nuevo", methods=["GET", "POST"])
@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def form(id=None):
    cliente = db.get_or_404(Cliente, id) if id else Cliente()
    if request.method == "POST":
        for campo in CAMPOS_CLIENTE:
            setattr(cliente, campo, _texto(campo))
        if not cliente.nombre:
            flash("El nombre es obligatorio.", "error")
        else:
            db.session.add(cliente)
            db.session.commit()
            flash("Cliente guardado.", "ok")
            return redirect(url_for(".detalle", id=cliente.id))
    return render_template("clientes/form.html", cliente=cliente, condiciones=CONDICIONES_IVA)


@bp.route("/<int:id>")
def detalle(id):
    cliente = db.get_or_404(Cliente, id)
    return render_template("clientes/detalle.html", cliente=cliente)


@bp.route("/<int:cliente_id>/vehiculos/nuevo", methods=["GET", "POST"])
@bp.route("/vehiculos/<int:id>/editar", methods=["GET", "POST"])
def vehiculo_form(cliente_id=None, id=None):
    if id:
        vehiculo = db.get_or_404(Vehiculo, id)
    else:
        vehiculo = Vehiculo(cliente=db.get_or_404(Cliente, cliente_id))
    if request.method == "POST":
        patente = (_texto("patente") or "").upper().replace(" ", "")
        with db.session.no_autoflush:
            duplicado = Vehiculo.query.filter(Vehiculo.patente == patente, Vehiculo.id != vehiculo.id).first()
        if not patente:
            flash("La patente es obligatoria.", "error")
        elif duplicado:
            flash(f"La patente {patente} ya está cargada ({duplicado.cliente.nombre}).", "error")
        else:
            vehiculo.patente = patente
            for campo in CAMPOS_VEHICULO:
                setattr(vehiculo, campo, _texto(campo))
            vehiculo.anio = _entero("anio")
            vehiculo.kilometraje = _entero("kilometraje")
            db.session.add(vehiculo)
            db.session.commit()
            flash("Vehículo guardado.", "ok")
            return redirect(url_for(".detalle", id=vehiculo.cliente_id))
    return render_template("clientes/vehiculo_form.html", vehiculo=vehiculo)


@bp.route("/vehiculos/<int:id>/eliminar", methods=["POST"])
def vehiculo_eliminar(id):
    vehiculo = db.get_or_404(Vehiculo, id)
    if vehiculo.ordenes:
        abort(400, "El vehículo tiene órdenes de trabajo; no se puede eliminar.")
    cliente_id = vehiculo.cliente_id
    db.session.delete(vehiculo)
    db.session.commit()
    flash("Vehículo eliminado.", "ok")
    return redirect(url_for(".detalle", id=cliente_id))


@bp.route("/vehiculos")
def vehiculos():
    q = request.args.get("q", "").strip()
    consulta = Vehiculo.query.join(Cliente)
    if q:
        like = f"%{q}%"
        consulta = consulta.filter(or_(Vehiculo.patente.ilike(like), Vehiculo.marca.ilike(like),
                                       Vehiculo.modelo.ilike(like), Cliente.nombre.ilike(like)))
    vehiculos = consulta.order_by(Vehiculo.patente).all()
    return render_template("clientes/vehiculos.html", vehiculos=vehiculos, q=q)
