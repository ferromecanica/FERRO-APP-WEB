from datetime import date

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..extensions import db
from ..models import ESTADOS_OT_ABIERTA, ConfigTaller, OrdenTrabajo, Repuesto, Socio, Turno, Venta
from ..services import drive
from ..validaciones import numero_ar

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    ventas_mes = Venta.query.filter(Venta.fecha >= inicio_mes).all()
    ots_abiertas = OrdenTrabajo.query.filter(OrdenTrabajo.estado.in_(ESTADOS_OT_ABIERTA)) \
        .order_by(OrdenTrabajo.fecha_ingreso).all()
    turnos = Turno.query.filter(Turno.fecha >= hoy, Turno.estado != "Cancelado") \
        .order_by(Turno.fecha, Turno.hora).limit(6).all()
    bajo_stock = [r for r in Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).all() if r.bajo_stock]

    por_cobrar = OrdenTrabajo.query.filter(OrdenTrabajo.estado == "Finalizada", ~OrdenTrabajo.ventas.any(),
                                           OrdenTrabajo.sin_cargo.is_(False)).all()
    valor_hora = ConfigTaller.get().valor_hora or 0
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
        cant_por_cobrar=len(por_cobrar),
        monto_por_cobrar=sum(o.horas_insumidas * valor_hora + o.total_repuestos for o in por_cobrar),
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
    from ..services.backup import ultimo_envio

    return render_template("dashboard/configuracion.html", cfg=cfg,
                           socios=Socio.query.order_by(Socio.orden, Socio.nombre).all(),
                           ultimo_backup=ultimo_envio(current_app.instance_path),
                           drive_ok=drive.configurado())


@bp.route("/configuracion/socios", methods=["POST"])
@login_required
def socios_guardar():
    """Sueldo base, participación y orden de cobro de cada socio."""
    nuevo = request.form.get("nombre_nuevo", "").strip()
    if nuevo:
        if Socio.query.filter(db.func.lower(Socio.nombre) == nuevo.lower()).first():
            flash("Ya hay un socio con ese nombre.", "error")
        else:
            db.session.add(Socio(nombre=nuevo, orden=(db.session.query(db.func.max(Socio.orden)).scalar() or 0) + 1))
    for socio in Socio.query.all():
        if request.form.get(f"borrar_{socio.id}"):
            if socio.aportes:
                flash(f"{socio.nombre} tiene aportes cargados: no se puede borrar.", "error")
            else:
                db.session.delete(socio)
            continue
        socio.rol = request.form.get(f"rol_{socio.id}", "").strip() or None
        socio.alias = request.form.get(f"alias_{socio.id}", "").strip() or None
        socio.sueldo_base = numero_ar(request.form.get(f"sueldo_{socio.id}")) or 0
        porcentaje = numero_ar(request.form.get(f"participacion_{socio.id}"))
        socio.participacion = (porcentaje / 100) if porcentaje is not None else socio.participacion
        socio.orden = request.form.get(f"orden_{socio.id}", type=int) or socio.orden
    db.session.commit()
    flash("Socios guardados.", "ok")
    return redirect(url_for(".configuracion") + "#socios")


@bp.route("/configuracion/backup", methods=["POST"])
@login_required
def backup_ahora():
    """Manda la copia a Drive en el momento (la de todos los días sale sola)."""
    from ..services.backup import mandar_a_drive

    try:
        nombre = mandar_a_drive(current_app._get_current_object())
        flash(f"Copia guardada en Drive: {nombre}.", "ok")
    except Exception as e:
        flash(f"No pude mandar la copia a Drive: {e}", "error")
    return redirect(url_for(".configuracion"))
