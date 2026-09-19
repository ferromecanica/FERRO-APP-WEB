from datetime import date, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    CLASIFICACIONES_CIERRE,
    ESTADOS_OT,
    ESTADOS_OT_ABIERTA,
    METODOS_PAGO,
    Cliente,
    ConfigTaller,
    ConsumoOT,
    OrdenTrabajo,
    RegistroHoras,
    Repuesto,
    TareaOT,
    Vehiculo,
    Venta,
    VentaItem,
)
from ..services.stock import buscar_repuesto, consumir_en_ot, repuesto_varios, revertir_consumo
from ..validaciones import MARCAS_COMUNES, normalizar_patente, numero_ar, patente_valida

bp = Blueprint("ot", __name__)

CHECKLIST = [
    ("aceite_motor", "Aceite de motor", "aceite_motor_detalle"),
    ("aceite_caja", "Aceite de caja", "aceite_caja_detalle"),
    ("aceite_diferencial", "Aceite de diferencial", "aceite_diferencial_detalle"),
    ("filtro_aceite", "Filtro de aceite", None),
    ("filtro_aire", "Filtro de aire", None),
    ("filtro_habitaculo", "Filtro de habitáculo", None),
    ("filtro_combustible", "Filtro de combustible", None),
    ("scaneo", "Escaneo", None),
]


@bp.before_request
@login_required
def _requiere_login():
    pass


def _ot_editable(id):
    """Devuelve la OT si está abierta; si está cerrada, None (y avisa)."""
    ot = db.get_or_404(OrdenTrabajo, id)
    if not ot.abierta:
        flash("La OT está cerrada. Reabrila para modificarla.", "error")
        return None
    return ot


def _volver(ot_o_id, seccion=None):
    ot_id = ot_o_id if isinstance(ot_o_id, int) else ot_o_id.id
    return redirect(url_for(".detalle", id=ot_id) + (f"#{seccion}" if seccion else ""))


def _fecha(campo, defecto=None):
    try:
        return datetime.strptime(request.form.get(campo, ""), "%Y-%m-%d").date()
    except ValueError:
        return defecto


def _mecanicos():
    usados = [m for (m,) in db.session.query(RegistroHoras.mecanico).distinct() if m]
    return sorted(set(usados) | {"Iván", "Lucio"})


# ─────────────────────────────── Listado y alta ─────────────────────────────


@bp.route("/")
def lista():
    estado = request.args.get("estado")
    q = request.args.get("q", "").strip()
    consulta = OrdenTrabajo.query.join(Vehiculo).outerjoin(Cliente, OrdenTrabajo.cliente_id == Cliente.id)
    if estado == "abiertas":
        consulta = consulta.filter(OrdenTrabajo.estado.in_(ESTADOS_OT_ABIERTA))
    elif estado:
        consulta = consulta.filter(OrdenTrabajo.estado == estado)
    if q:
        like = f"%{q}%"
        filtros = [Vehiculo.patente.ilike(like), Cliente.nombre.ilike(like), OrdenTrabajo.detalle.ilike(like),
                   Vehiculo.modelo.ilike(like)]
        if q.isdigit():
            filtros.append(OrdenTrabajo.id == int(q))
        consulta = consulta.filter(or_(*filtros))
    ordenes = consulta.order_by(OrdenTrabajo.id.desc()).all()
    plantilla = "ot/_tabla.html" if request.headers.get("HX-Request") else "ot/lista.html"
    return render_template(plantilla, ordenes=ordenes, estados=ESTADOS_OT, estado=estado, q=q,
                           valor_hora=ConfigTaller.get().valor_hora or 0)


def _buscar_cliente(texto):
    """Resuelve lo escrito en el campo Cliente: 'Nombre · CLI-003', o un nombre exacto."""
    texto = (texto or "").strip()
    if "CLI-" in texto:
        codigo = texto.rsplit("CLI-", 1)[1].strip()
        if codigo.isdigit():
            return db.session.get(Cliente, int(codigo))
    coincidencias = Cliente.query.filter(db.func.lower(Cliente.nombre) == texto.lower()).all()
    return coincidencias[0] if len(coincidencias) == 1 else None


@bp.route("/vehiculo")
def vehiculo_info():
    """Datos de una patente para el formulario de nueva OT (lo pide el navegador al tipear)."""
    patente = normalizar_patente(request.args.get("patente"))
    v = Vehiculo.query.filter_by(patente=patente).first() if patente else None
    if v is None:
        return jsonify(existe=False, patente=patente, valida=patente_valida(patente))
    return jsonify(
        existe=True, patente=v.patente, descripcion=v.descripcion, km=v.kilometraje,
        cliente=v.cliente.etiqueta if v.cliente else None,
    )


@bp.route("/nueva", methods=["GET", "POST"])
@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def form(id=None):
    ot = db.get_or_404(OrdenTrabajo, id) if id else OrdenTrabajo(fecha_ingreso=date.today())
    if id and not ot.abierta:
        flash("La OT está cerrada. Reabrila para modificarla.", "error")
        return _volver(ot)
    vehiculo = ot.vehiculo
    if not id and request.args.get("vehiculo_id", type=int):
        vehiculo = db.session.get(Vehiculo, request.args.get("vehiculo_id", type=int))

    if request.method == "POST":
        errores = []
        if not id:
            vehiculo, errores = _resolver_vehiculo()
        cliente, errores_cliente = _resolver_cliente(obligatorio=False)
        errores += errores_cliente
        km = numero_ar(request.form.get("km_entrada"))
        ot.km_entrada = int(km) if km is not None else None
        ot.detalle = request.form.get("detalle", "").strip() or None
        ot.presupuesto_cliente = numero_ar(request.form.get("presupuesto_cliente"))
        ot.fecha_ingreso = _fecha("fecha_ingreso", ot.fecha_ingreso or date.today())
        if not ot.detalle:
            errores.append("Contá qué trae el auto (motivo de ingreso).")
        if errores:
            db.session.rollback()
            for e in errores:
                flash(e, "error")
        else:
            if not id:
                ot.id = OrdenTrabajo.proximo_numero()
                ot.vehiculo = vehiculo
                ot.estado = "Ingresado"
                db.session.add(ot)
            _asignar_cliente(ot, cliente)
            if ot.km_entrada and ot.km_entrada > (ot.vehiculo.kilometraje or 0):
                ot.vehiculo.kilometraje = ot.km_entrada
            db.session.commit()
            flash(f"OT #{ot.id} {'creada' if not id else 'guardada'}.", "ok")
            return _volver(ot)

    vehiculos = marcas = []
    if not id:
        vehiculos = Vehiculo.query.outerjoin(Cliente).order_by(Vehiculo.patente).all()
        cargadas = {m for (m,) in db.session.query(Vehiculo.marca).distinct() if m}
        marcas = sorted(set(MARCAS_COMUNES) | cargadas, key=str.lower)
    return render_template("ot/form.html", ot=ot, vehiculo=vehiculo, vehiculos=vehiculos, clientes=_clientes(),
                           marcas=marcas, proximo=OrdenTrabajo.proximo_numero())


def _clientes():
    return Cliente.query.order_by(db.func.lower(Cliente.nombre)).all()


def _asignar_cliente(ot, cliente):
    """Pone el cliente en la OT y asocia el vehículo a ese cliente (si tenía otro dueño, lo avisa)."""
    if cliente is None:
        if not ot.cliente and ot.vehiculo.cliente:
            ot.cliente = ot.vehiculo.cliente  # sin cliente elegido: el dueño del auto
        return
    ot.cliente = cliente
    vehiculo = ot.vehiculo
    if vehiculo.cliente is not cliente:
        if vehiculo.cliente is not None:
            flash(f"{vehiculo.patente} pasó de {vehiculo.cliente.nombre} a {cliente.nombre}.", "info")
        vehiculo.cliente = cliente


def _resolver_vehiculo():
    """Del formulario de nueva OT: busca el vehículo por patente o lo da de alta (solo el vehículo)."""
    patente = normalizar_patente(request.form.get("patente"))
    vehiculo = Vehiculo.query.filter_by(patente=patente).first() if patente else None
    if vehiculo is not None:
        return vehiculo, []
    if not patente_valida(patente):
        return None, [f"La patente «{request.form.get('patente', '')}» no parece válida."]
    anio = request.form.get("v_anio", "").strip()
    vehiculo = Vehiculo(
        patente=patente,
        marca=request.form.get("v_marca", "").strip() or None,
        modelo=request.form.get("v_modelo", "").strip() or None,
        motor=request.form.get("v_motor", "").strip() or None,
        anio=int(anio) if anio.isdigit() else None,
    )
    db.session.add(vehiculo)
    return vehiculo, []


def _resolver_cliente(obligatorio):
    """Del campo Cliente: uno existente, uno nuevo (alta solo del cliente) o ninguno."""
    texto = request.form.get("cliente", "").strip()
    if not texto:
        return None, (["Indicá el cliente."] if obligatorio else [])
    cliente = _buscar_cliente(texto)
    if cliente is not None:
        return cliente, []
    if "CLI-" in texto:
        return None, [f"No encontré el cliente «{texto}»."]
    cliente = Cliente(nombre=texto, telefono=request.form.get("c_telefono", "").strip() or None)
    db.session.add(cliente)
    return cliente, []


@bp.route("/<int:id>")
def detalle(id):
    ot = db.get_or_404(OrdenTrabajo, id)
    valor_hora = ConfigTaller.get().valor_hora or 0
    mano_obra = ot.horas_insumidas * valor_hora
    repuestos = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).order_by(Repuesto.nombre).all()
    return render_template(
        "ot/detalle.html", ot=ot, estados=ESTADOS_OT_ABIERTA, checklist=CHECKLIST, mecanicos=_mecanicos(),
        repuestos=repuestos, valor_hora=valor_hora, mano_obra=mano_obra,
        total_calculado=mano_obra + ot.total_repuestos,
    )


@bp.route("/<int:id>/estado", methods=["POST"])
def cambiar_estado(id):
    ot = _ot_editable(id)
    if ot is None:
        return redirect(url_for(".detalle", id=id))
    nuevo = request.form.get("estado")
    if nuevo in ESTADOS_OT_ABIERTA:
        ot.estado = nuevo
        db.session.commit()
    return _volver(ot)


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    ot = _ot_editable(id)
    if ot is None:
        return redirect(url_for(".detalle", id=id))
    for consumo in list(ot.consumos):
        revertir_consumo(consumo)
    db.session.flush()
    db.session.expire(ot, ["consumos"])  # ya borrados: que el cascade no los borre otra vez
    db.session.delete(ot)
    db.session.commit()
    flash(f"OT #{id} eliminada. Los repuestos volvieron al stock.", "ok")
    return redirect(url_for(".lista"))


# ─────────────────────────────── Tareas y horas ─────────────────────────────


@bp.route("/<int:id>/tareas", methods=["POST"])
def tarea_agregar(id):
    ot = _ot_editable(id)
    if ot is None:
        return redirect(url_for(".detalle", id=id))
    texto = request.form.get("descripcion", "").strip()
    if texto:
        db.session.add(TareaOT(ot=ot, descripcion=texto))
        db.session.commit()
    return _volver(ot, "tareas")


@bp.route("/tareas/<int:tid>/eliminar", methods=["POST"])
def tarea_eliminar(tid):
    tarea = db.get_or_404(TareaOT, tid)
    ot_id = tarea.ot_id
    ot = _ot_editable(ot_id)
    if ot is not None:
        db.session.delete(tarea)
        db.session.commit()
    return _volver(ot_id, "tareas")


@bp.route("/<int:id>/horas", methods=["POST"])
def horas_agregar(id):
    ot = _ot_editable(id)
    if ot is None:
        return redirect(url_for(".detalle", id=id))
    horas = numero_ar(request.form.get("horas"))
    mecanico = request.form.get("mecanico", "").strip()
    if not horas or horas <= 0 or not mecanico:
        flash("Indicá mecánico y horas.", "error")
    else:
        db.session.add(RegistroHoras(ot=ot, mecanico=mecanico, horas=horas, fecha=_fecha("fecha", date.today()),
                                     detalle=request.form.get("detalle", "").strip() or None))
        db.session.commit()
    return _volver(ot, "horas")


@bp.route("/horas/<int:hid>/eliminar", methods=["POST"])
def horas_eliminar(hid):
    registro = db.get_or_404(RegistroHoras, hid)
    ot_id = registro.ot_id
    ot = _ot_editable(ot_id)
    if ot is not None:
        db.session.delete(registro)
        db.session.commit()
    return _volver(ot_id, "horas")


# ────────────────────────────────── Repuestos ───────────────────────────────


@bp.route("/<int:id>/repuestos", methods=["POST"])
def repuesto_agregar(id):
    ot = _ot_editable(id)
    if ot is None:
        return redirect(url_for(".detalle", id=id))
    cantidad = numero_ar(request.form.get("cantidad")) or 1
    if cantidad <= 0:
        flash("La cantidad tiene que ser mayor a cero.", "error")
        return _volver(ot, "repuestos")

    if request.form.get("tipo") == "varios":
        descripcion = request.form.get("descripcion", "").strip()
        precio = numero_ar(request.form.get("precio"))
        if not descripcion or precio is None:
            flash("Para un ítem varios poné descripción y precio.", "error")
            return _volver(ot, "repuestos")
        consumir_en_ot(ot, repuesto_varios(), cantidad, precio_unitario=precio, descripcion=descripcion,
                       precio_costo=numero_ar(request.form.get("costo")) or 0)
    else:
        texto = request.form.get("repuesto", "").strip()
        codigo = texto.split("·")[0].strip()
        repuesto = db.session.get(Repuesto, int(codigo)) if codigo.isdigit() else None
        repuesto = repuesto or buscar_repuesto(texto)
        if repuesto is None or repuesto.id == Repuesto.ID_VARIOS:
            flash(f"No encontré el repuesto «{texto}».", "error")
            return _volver(ot, "repuestos")
        if repuesto.stock_actual < cantidad:
            flash(f"Ojo: {repuesto.nombre} queda con stock negativo ({repuesto.stock_actual - cantidad:g}).", "info")
        consumir_en_ot(ot, repuesto, cantidad)
    db.session.commit()
    return _volver(ot, "repuestos")


@bp.route("/consumos/<int:cid>/eliminar", methods=["POST"])
def consumo_eliminar(cid):
    consumo = db.get_or_404(ConsumoOT, cid)
    ot_id = consumo.ot_id
    ot = _ot_editable(ot_id)
    if ot is not None:
        revertir_consumo(consumo)
        db.session.commit()
    return _volver(ot_id, "repuestos")


# ────────────────────────────────── Checklist ───────────────────────────────


@bp.route("/<int:id>/checklist", methods=["POST"])
def checklist(id):
    ot = _ot_editable(id)
    if ot is None:
        return redirect(url_for(".detalle", id=id))
    for campo, _, detalle in CHECKLIST:
        setattr(ot, campo, bool(request.form.get(campo)))
        if detalle:
            setattr(ot, detalle, request.form.get(detalle, "").strip() or None)
    km = numero_ar(request.form.get("km_proximo_service"))
    ot.km_proximo_service = int(km) if km else None
    ot.otros = request.form.get("otros", "").strip() or None
    db.session.commit()
    flash("Checklist guardado.", "ok")
    return _volver(ot, "checklist")


# ──────────────────────────────── Cierre de OT ──────────────────────────────


@bp.route("/<int:id>/cerrar", methods=["GET", "POST"])
def cerrar(id):
    ot = _ot_editable(id)
    if ot is None:
        return redirect(url_for(".detalle", id=id))
    valor_hora = ConfigTaller.get().valor_hora or 0
    total_calculado = ot.horas_insumidas * valor_hora + ot.total_repuestos

    if request.method == "POST":
        cobrado = numero_ar(request.form.get("total_cobrado"))
        metodo = request.form.get("metodo_pago")
        errores = []
        if ot.cliente is None:
            cliente, errores = _resolver_cliente(obligatorio=True)
        if cobrado is None or cobrado < 0 or metodo not in METODOS_PAGO:
            errores.append("Completá el total cobrado y la forma de pago.")
        if errores:
            db.session.rollback()
            for e in errores:
                flash(e, "error")
        else:
            if ot.cliente is None:
                _asignar_cliente(ot, cliente)
            ot.total_cobrado = cobrado
            ot.fecha_fin = _fecha("fecha_fin", date.today())
            ot.clasificacion_cierre = request.form.get("clasificacion") or None
            ot.estado = "Terminado"
            venta = Venta(fecha=ot.fecha_fin, cliente=ot.cliente, ot=ot, metodo_pago=metodo)
            venta.items.append(VentaItem(
                descripcion=f"{ot.detalle or 'Trabajo'} - OT {ot.id}", cantidad=1,
                precio_unitario=cobrado, costo_unitario=ot.costo_repuestos,
            ))
            db.session.add(venta)
            db.session.commit()
            flash(f"OT #{ot.id} cerrada. Venta registrada por ${cobrado:,.0f}.".replace(",", "."), "ok")
            return _volver(ot)
    es_service = any(getattr(ot, campo) for campo, _, _ in CHECKLIST)
    return render_template("ot/cerrar.html", ot=ot, total_calculado=total_calculado, valor_hora=valor_hora,
                           metodos=METODOS_PAGO, clasificaciones=CLASIFICACIONES_CIERRE,
                           sugerida="Servicio" if es_service else "Otro",
                           clientes=_clientes() if ot.cliente is None else [])


@bp.route("/<int:id>/entregar", methods=["POST"])
def entregar(id):
    ot = db.get_or_404(OrdenTrabajo, id)
    if ot.estado == "Terminado":
        ot.estado = "Entregado"
        db.session.commit()
    return _volver(ot)


@bp.route("/<int:id>/reabrir", methods=["POST"])
def reabrir(id):
    ot = db.get_or_404(OrdenTrabajo, id)
    if not ot.abierta:
        for venta in list(ot.ventas):
            db.session.delete(venta)
        ot.estado = "En reparación"
        ot.fecha_fin = None
        ot.total_cobrado = None
        db.session.commit()
        flash(f"OT #{ot.id} reabierta. Se anuló la venta asociada.", "info")
    return _volver(ot)
