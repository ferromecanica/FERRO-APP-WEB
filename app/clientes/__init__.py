from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func, or_

from ..extensions import db
from ..models import Cliente, Presupuesto, Turno, Vehiculo, Venta
from ..validaciones import (
    CONDICIONES_IVA,
    MARCAS_COMUNES,
    cuit_valido,
    formatear_cuit,
    FORMATOS_PATENTE,
    SIN_PATENTE,
    normalizar_patente,
    patente_valida,
)

bp = Blueprint("clientes", __name__)

CAMPOS_CLIENTE = ["nombre", "telefono", "email", "direccion", "condicion_iva", "notas"]
CAMPOS_VEHICULO = ["marca", "modelo", "motor", "traccion", "color", "vin", "ecu_marca", "ecu_modelo"]


def _texto(campo, prefijo=""):
    return request.form.get(prefijo + campo, "").strip() or None


def _entero(campo, prefijo=""):
    valor = request.form.get(prefijo + campo, "").replace(".", "").strip()
    return int(valor) if valor.isdigit() else None


def _marcas():
    """Marcas comunes + las que ya están cargadas, para sugerir al tipear."""
    cargadas = {m for (m,) in db.session.query(Vehiculo.marca).distinct() if m}
    return sorted(set(MARCAS_COMUNES) | cargadas, key=str.lower)


def _cargar_cliente(cliente):
    """Pasa el formulario al cliente. Devuelve la lista de errores."""
    for campo in CAMPOS_CLIENTE:
        setattr(cliente, campo, _texto(campo))
    cuit = _texto("cuit")
    cliente.cuit = formatear_cuit(cuit) if cuit else None
    errores = []
    if not cliente.nombre:
        errores.append("El nombre es obligatorio.")
    if cuit and not cuit_valido(cuit):
        errores.append("El CUIT no es válido (revisá los 11 números).")
    return errores


def _cargar_vehiculo(vehiculo, prefijo=""):
    """Pasa el formulario al vehículo. Devuelve la lista de errores."""
    patente = normalizar_patente(_texto("patente", prefijo))
    errores = []
    if not patente:
        errores.append("La patente es obligatoria.")
    elif not patente_valida(patente):
        errores.append(f"«{patente}» no tiene formato de patente. Va {FORMATOS_PATENTE}.")
    elif patente != SIN_PATENTE:  # puede haber más de un auto sin chapa
        with db.session.no_autoflush:
            duplicado = Vehiculo.query.filter(Vehiculo.patente == patente, Vehiculo.id != vehiculo.id).first()
        if duplicado:
            dueno = f" a nombre de {duplicado.cliente.nombre}" if duplicado.cliente else ""
            errores.append(f"La patente {patente} ya está cargada{dueno}.")
    vehiculo.patente = patente
    for campo in CAMPOS_VEHICULO:
        setattr(vehiculo, campo, _texto(campo, prefijo))
    vehiculo.anio = _entero("anio", prefijo)
    vehiculo.kilometraje = _entero("kilometraje", prefijo)
    return errores


@bp.before_request
@login_required
def _requiere_login():
    pass


# ─────────────────────────────────── Clientes ───────────────────────────────


@bp.route("/")
def lista():
    q = request.args.get("q", "").strip()
    consulta = Cliente.query
    if q:
        like = f"%{q}%"
        consulta = consulta.outerjoin(Vehiculo).filter(
            or_(Cliente.nombre.ilike(like), Cliente.telefono.ilike(like), Vehiculo.patente.ilike(like),
                Cliente.cuit.ilike(like), Cliente.notas.ilike(like), Vehiculo.marca.ilike(like),
                Vehiculo.modelo.ilike(like))
        ).distinct()
    clientes = consulta.order_by(Cliente.nombre).all()
    plantilla = "clientes/_tabla.html" if request.headers.get("HX-Request") else "clientes/lista.html"
    return render_template(plantilla, clientes=clientes, q=q)


@bp.route("/nuevo", methods=["GET", "POST"])
@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def form(id=None):
    cliente = db.get_or_404(Cliente, id) if id else Cliente()
    if request.method == "POST":
        errores = _cargar_cliente(cliente)
        if errores:
            for e in errores:
                flash(e, "error")
        else:
            db.session.add(cliente)
            db.session.commit()
            flash("Cliente guardado.", "ok")
            return redirect(url_for(".detalle", id=cliente.id))
    return render_template("clientes/form.html", cliente=cliente, condiciones=CONDICIONES_IVA)


@bp.route("/<int:id>")
def detalle(id):
    cliente = db.get_or_404(Cliente, id)
    return render_template("clientes/detalle.html", cliente=cliente, bloqueos=_bloqueos_borrado(cliente))


def _bloqueos_borrado(cliente):
    """Motivos por los que no se puede borrar el cliente (vacío = se puede)."""
    motivos = []
    if cliente.ordenes:
        motivos.append(f"{len(cliente.ordenes)} órdenes de trabajo")
    n = Presupuesto.query.filter_by(cliente_id=cliente.id).count()
    if n:
        motivos.append(f"{n} presupuestos")
    n = Venta.query.filter_by(cliente_id=cliente.id).count()
    if n:
        motivos.append(f"{n} ventas")
    return motivos


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    cliente = db.get_or_404(Cliente, id)
    bloqueos = _bloqueos_borrado(cliente)
    if bloqueos:
        flash("No se puede eliminar: tiene " + ", ".join(bloqueos) + ".", "error")
        return redirect(url_for(".detalle", id=id))
    Turno.query.filter_by(cliente_id=id).update({"cliente_id": None, "contacto": cliente.nombre})
    for v in list(cliente.vehiculos):
        v.cliente = None  # el auto sigue existiendo, sin dueño asignado
    db.session.delete(cliente)
    db.session.commit()
    flash(f"Cliente {cliente.nombre} eliminado.", "ok")
    return redirect(url_for(".lista"))


# ─────────────────────────────────── Vehículos ──────────────────────────────


@bp.route("/vehiculos")
def vehiculos():
    q = request.args.get("q", "").strip()
    consulta = Vehiculo.query.outerjoin(Cliente)
    if q:
        like = f"%{q}%"
        consulta = consulta.filter(or_(Vehiculo.patente.ilike(like), Vehiculo.marca.ilike(like),
                                       Vehiculo.modelo.ilike(like), Cliente.nombre.ilike(like)))
    vehiculos = consulta.order_by(Vehiculo.patente).all()
    plantilla = "clientes/_tabla_vehiculos.html" if request.headers.get("HX-Request") else "clientes/vehiculos.html"
    return render_template(plantilla, vehiculos=vehiculos, q=q)


@bp.route("/vehiculos/<int:id>")
def vehiculo_detalle(id):
    vehiculo = db.get_or_404(Vehiculo, id)
    # Evolución de km: lo registrado en cada OT (de la más vieja a la más nueva)
    lecturas = [(ot.fecha_ingreso, ot.km_entrada, ot.id) for ot in reversed(vehiculo.ordenes) if ot.km_entrada]
    return render_template("clientes/vehiculo_detalle.html", vehiculo=vehiculo, lecturas=lecturas)


@bp.route("/vehiculos/nuevo", methods=["GET", "POST"])
@bp.route("/<int:cliente_id>/vehiculos/nuevo", methods=["GET", "POST"])
@bp.route("/vehiculos/<int:id>/editar", methods=["GET", "POST"])
def vehiculo_form(cliente_id=None, id=None):
    if id:
        vehiculo = db.get_or_404(Vehiculo, id)
    else:
        vehiculo = Vehiculo(cliente_id=cliente_id)
    if request.method == "POST":
        errores = _cargar_vehiculo(vehiculo)
        nuevo_dueno = request.form.get("cliente_id", type=int)
        if nuevo_dueno != vehiculo.cliente_id:
            if nuevo_dueno and db.session.get(Cliente, nuevo_dueno) is None:
                errores.append("El cliente elegido no existe.")
            elif vehiculo.id and vehiculo.cliente_id and vehiculo.ordenes:
                flash("Cambio de dueño registrado. Las OT anteriores quedan con el dueño que tenían.", "info")
            vehiculo.cliente_id = nuevo_dueno
        if errores:
            for e in errores:
                flash(e, "error")
        else:
            db.session.add(vehiculo)
            db.session.commit()
            flash(f"Vehículo {vehiculo.patente} guardado.", "ok")
            return redirect(url_for(".vehiculo_detalle", id=vehiculo.id))
    clientes = Cliente.query.order_by(func.lower(Cliente.nombre)).all()
    return render_template("clientes/vehiculo_form.html", vehiculo=vehiculo, clientes=clientes, marcas=_marcas(),
                           dueno=db.session.get(Cliente, vehiculo.cliente_id) if vehiculo.cliente_id else None)


@bp.route("/vehiculos/<int:id>/eliminar", methods=["POST"])
def vehiculo_eliminar(id):
    vehiculo = db.get_or_404(Vehiculo, id)
    cliente_id = vehiculo.cliente_id
    if vehiculo.ordenes:
        flash("El vehículo tiene órdenes de trabajo; no se puede eliminar.", "error")
        return redirect(url_for(".vehiculo_detalle", id=id))
    Turno.query.filter_by(vehiculo_id=id).update({"vehiculo_id": None})
    db.session.delete(vehiculo)
    db.session.commit()
    flash(f"Vehículo {vehiculo.patente} eliminado.", "ok")
    return redirect(url_for(".detalle", id=cliente_id) if cliente_id else url_for(".vehiculos"))
