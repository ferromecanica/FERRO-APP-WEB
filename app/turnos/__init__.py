"""Turnos: la agenda del taller. De un turno sale después la OT."""
import calendar
from datetime import date, datetime, time, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..extensions import db
from ..models import ESTADOS_TURNO, Cliente, Turno, Vehiculo
from ..validaciones import numero_ar

bp = Blueprint("turnos", __name__)

VISTAS = {
    "proximos": "Próximos",
    "hoy": "Hoy",
    "semana": "Esta semana",
    "pasados": "Pasados",
    "todos": "Todos",
    "mes": "Almanaque",
}
DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


@bp.before_request
@login_required
def _requiere_login():
    pass


def _clientes():
    return Cliente.query.order_by(db.func.lower(Cliente.nombre)).all()


def _datos_comunes():
    clientes = _clientes()
    return {
        "clientes": clientes,
        "vehiculos_por_cliente": {c.id: [{"id": v.id, "texto": f"{v.patente} · {v.descripcion}".strip(" ·")}
                                         for v in c.vehiculos] for c in clientes},
        "estados": ESTADOS_TURNO,
    }


def _mes_pedido():
    """El mes que se está mirando en el almanaque (YYYY-MM), o el actual."""
    try:
        return datetime.strptime(request.args["mes"], "%Y-%m").date().replace(day=1)
    except (KeyError, ValueError):
        return date.today().replace(day=1)


def _sumar_meses(mes, cuantos):
    total = mes.month - 1 + cuantos
    return date(mes.year + total // 12, total % 12 + 1, 1)


@bp.route("/")
def lista():
    hoy = date.today()
    vista = request.args.get("vista", "proximos")
    q = request.args.get("q", "").strip()
    if vista == "mes":
        return _almanaque(hoy, q)

    consulta = Turno.query.outerjoin(Cliente).outerjoin(Vehiculo, Turno.vehiculo_id == Vehiculo.id)
    elegido = None
    if vista == "dia":
        try:
            elegido = datetime.strptime(request.args.get("fecha", ""), "%Y-%m-%d").date()
        except ValueError:
            elegido = hoy
        consulta = consulta.filter(Turno.fecha == elegido)
    elif vista == "hoy":
        consulta = consulta.filter(Turno.fecha == hoy)
    elif vista == "semana":
        consulta = consulta.filter(Turno.fecha >= hoy, Turno.fecha <= hoy + timedelta(days=7))
    elif vista == "pasados":
        consulta = consulta.filter(Turno.fecha < hoy)
    elif vista != "todos":
        vista = "proximos"
        consulta = consulta.filter(Turno.fecha >= hoy, Turno.estado != "Cancelado")
    if q:
        like = f"%{q}%"
        consulta = consulta.filter(db.or_(Cliente.nombre.ilike(like), Turno.contacto.ilike(like),
                                          Turno.motivo.ilike(like), Vehiculo.patente.ilike(like),
                                          Turno.telefono.ilike(like)))

    orden = (Turno.fecha.desc(), Turno.hora.desc()) if vista == "pasados" else (Turno.fecha, Turno.hora)
    turnos = consulta.order_by(*orden).all()

    # agrupados por día, que es como se mira una agenda
    dias = []
    for turno in turnos:
        if not dias or dias[-1]["fecha"] != turno.fecha:
            dias.append({"fecha": turno.fecha, "turnos": []})
        dias[-1]["turnos"].append(turno)
    return render_template("turnos/lista.html", dias=dias, vista=vista, vistas=VISTAS, q=q,
                           cantidad=len(turnos), hoy=hoy, elegido=elegido)


def _almanaque(hoy, q):
    """Vista de mes: las semanas del mes con los turnos de cada día."""
    mes = _mes_pedido()
    siguiente = _sumar_meses(mes, 1)
    turnos = Turno.query.filter(Turno.fecha >= mes, Turno.fecha < siguiente).order_by(Turno.hora).all()
    por_dia = {}
    for turno in turnos:
        por_dia.setdefault(turno.fecha, []).append(turno)
    semanas = [[{"fecha": dia, "turnos": por_dia.get(dia, []), "del_mes": dia.month == mes.month}
                for dia in semana]
               for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(mes.year, mes.month)]
    return render_template("turnos/mes.html", semanas=semanas, mes=mes, hoy=hoy, q=q,
                           vista="mes", vistas=VISTAS, dias_semana=DIAS_SEMANA,
                           anterior=_sumar_meses(mes, -1), siguiente=siguiente,
                           cantidad=len(turnos))


def _hora(texto):
    try:
        return datetime.strptime(texto.strip(), "%H:%M").time()
    except (ValueError, AttributeError):
        return None


@bp.route("/nuevo", methods=["GET", "POST"])
@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def form(id=None):
    turno = db.get_or_404(Turno, id) if id else Turno(fecha=date.today(), hora=time(9, 0), estado="Confirmado")
    if request.method == "POST":
        fecha = request.form.get("fecha", "")
        try:
            turno.fecha = datetime.strptime(fecha, "%Y-%m-%d").date()
        except ValueError:
            flash("Poné la fecha del turno.", "error")
            return render_template("turnos/form.html", t=turno, **_datos_comunes())

        cliente = db.session.get(Cliente, request.form.get("cliente_id", type=int) or 0)
        vehiculo = db.session.get(Vehiculo, request.form.get("vehiculo_id", type=int) or 0)
        turno.cliente = cliente
        turno.vehiculo = vehiculo if vehiculo and (cliente is None or vehiculo.cliente_id == cliente.id) else None
        turno.hora = _hora(request.form.get("hora"))
        turno.contacto = request.form.get("contacto", "").strip() or None if cliente is None else None
        turno.telefono = request.form.get("telefono", "").strip() or None
        turno.motivo = request.form.get("motivo", "").strip() or None
        turno.observaciones = request.form.get("observaciones", "").strip() or None
        turno.duracion_valor = numero_ar(request.form.get("duracion_valor")) or None
        turno.duracion_unidad = request.form.get("duracion_unidad") if turno.duracion_valor else None
        if request.form.get("estado") in ESTADOS_TURNO:
            turno.estado = request.form.get("estado")
        if not turno.cliente and not turno.contacto:
            flash("Poné de quién es el turno: elegí un cliente o escribí el nombre.", "error")
            return render_template("turnos/form.html", t=turno, **_datos_comunes())

        if not id:
            db.session.add(turno)
        db.session.commit()
        flash("Turno guardado." if id else f"Turno del {turno.fecha:%d/%m} agendado.", "ok")
        return redirect(url_for(".lista", vista="proximos") + f"#turno-{turno.id}")

    return render_template("turnos/form.html", t=turno, **_datos_comunes())


@bp.route("/<int:id>/estado", methods=["POST"])
def estado(id):
    turno = db.get_or_404(Turno, id)
    nuevo = request.form.get("estado")
    if nuevo in ESTADOS_TURNO:
        turno.estado = nuevo
        db.session.commit()
        flash(f"Turno {nuevo.lower()}.", "ok")
    return redirect(request.form.get("volver") or url_for(".lista"))


@bp.route("/<int:id>/desenganchar", methods=["POST"])
def desenganchar(id):
    """Suelta la OT que se había enganchado sola a este turno (por si era otra)."""
    turno = db.get_or_404(Turno, id)
    if turno.ot is not None:
        numero = turno.ot.id
        turno.ot = None
        turno.estado = "Confirmado"
        db.session.commit()
        flash(f"El turno ya no está enganchado a la OT #{numero}.", "ok")
    return redirect(request.form.get("volver") or url_for(".lista"))


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    turno = db.get_or_404(Turno, id)
    db.session.delete(turno)
    db.session.commit()
    flash("Turno eliminado.", "ok")
    return redirect(url_for(".lista", vista=request.form.get("vista") or None))
