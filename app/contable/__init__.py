"""Administración: la plata del taller. Gastos, aportes de los socios y cierre del mes.

Los ingresos por ventas y las compras de repuestos no se cargan acá: se toman de
lo que ya está en Ferro, para no anotar dos veces lo mismo.
"""
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..extensions import db
from ..models import (
    CLASIFICACIONES,
    CierreMensual,
    CierreSocio,
    COMPROBANTES,
    TIPOS_CAPITAL,
    TIPOS_MOVIMIENTO_CONTABLE,
    AporteCapital,
    MovimientoContable,
    Socio,
)
from ..services import cierre as calculo
from ..validaciones import formatear_cuit, numero_ar

bp = Blueprint("contable", __name__)

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


@bp.before_request
@login_required
def _requiere_login():
    pass


def mes_lindo(mes):
    """'2026-08' → 'agosto de 2026'."""
    try:
        anio, numero = mes.split("-")
        return f"{MESES[int(numero) - 1]} de {anio}"
    except (ValueError, IndexError, AttributeError):
        return mes or "—"


@bp.app_template_filter("mes_imputacion")
def _filtro_mes(valor):
    return mes_lindo(valor)


def _clasificaciones():
    """Las de siempre, más las que se hayan escrito a mano."""
    usadas = {c for (c,) in db.session.query(MovimientoContable.clasificacion).distinct() if c}
    return CLASIFICACIONES + sorted(usadas - set(CLASIFICACIONES))


def _meses_cargados():
    """Los meses que tienen movimientos, del más nuevo al más viejo."""
    meses = [m for (m,) in db.session.query(MovimientoContable.mes_imputacion).distinct().all() if m]
    actual = MovimientoContable.mes_de(date.today())
    return sorted(set(meses) | {actual}, reverse=True)


# ───────────────────────────────── Movimientos ──────────────────────────────


@bp.route("/")
def movimientos():
    mes = request.args.get("mes") or MovimientoContable.mes_de(date.today())
    tipo = request.args.get("tipo", "")
    q = request.args.get("q", "").strip()

    consulta = MovimientoContable.query.filter_by(mes_imputacion=mes)
    if tipo in TIPOS_MOVIMIENTO_CONTABLE:
        consulta = consulta.filter(MovimientoContable.tipo == tipo)
    if q:
        like = f"%{q}%"
        consulta = consulta.filter(db.or_(MovimientoContable.quien.ilike(like),
                                          MovimientoContable.concepto.ilike(like),
                                          MovimientoContable.clasificacion.ilike(like),
                                          MovimientoContable.nro_comprobante.ilike(like)))
    movs = consulta.order_by(MovimientoContable.fecha.desc(), MovimientoContable.id.desc()).all()

    # Los números del mes, con el mismo criterio del cierre: los ingresos cuentan si están cobrados
    del_mes = MovimientoContable.query.filter_by(mes_imputacion=mes).all()
    ingresos = sum(m.total for m in del_mes if m.tipo == "Ingreso" and m.cobrado)
    por_cobrar = sum(m.total for m in del_mes if m.tipo == "Ingreso" and not m.cobrado)
    egresos = sum(m.total for m in del_mes if m.tipo == "Egreso"
                  and m.comprobante != "Liquidación" and m.clasificacion != "Inversión de Capital")
    colchon = sum(m.total for m in del_mes if m.tipo == "Colchón")
    return render_template(
        "contable/movimientos.html", movimientos=movs, mes=mes, meses=_meses_cargados(), tipo=tipo, q=q,
        tipos=TIPOS_MOVIMIENTO_CONTABLE,
        totales={"ingresos": ingresos, "por_cobrar": por_cobrar, "egresos": egresos, "colchon": colchon,
                 "resultado": ingresos - egresos + colchon},
    )


def _fecha(campo, defecto=None):
    try:
        return datetime.strptime(request.form.get(campo, ""), "%Y-%m-%d").date()
    except ValueError:
        return defecto


@bp.route("/nuevo", methods=["GET", "POST"])
@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def form(id=None):
    mov = db.get_or_404(MovimientoContable, id) if id else MovimientoContable(
        fecha=date.today(), tipo="Egreso", comprobante="S/C", cobrado=True)
    if id and mov.automatico:
        flash("Este movimiento salió de una venta o de una compra: se edita en su pantalla.", "error")
        return redirect(url_for(".movimientos", mes=mov.mes_imputacion))

    if request.method == "POST":
        mov.fecha = _fecha("fecha", mov.fecha or date.today())
        mov.tipo = request.form.get("tipo") if request.form.get("tipo") in TIPOS_MOVIMIENTO_CONTABLE else "Egreso"
        mov.mes_imputacion = request.form.get("mes_imputacion") or MovimientoContable.mes_de(mov.fecha)
        mov.clasificacion = request.form.get("clasificacion") or None
        mov.comprobante = request.form.get("comprobante") or "S/C"
        mov.nro_comprobante = request.form.get("nro_comprobante", "").strip() or None
        mov.quien = request.form.get("quien", "").strip() or None
        mov.cuit = formatear_cuit(request.form.get("cuit", "")) or None
        mov.concepto = request.form.get("concepto", "").strip() or None
        for campo in ("neto", "iva", "percepciones", "no_gravado"):
            setattr(mov, campo, numero_ar(request.form.get(campo)) or 0)
        total = numero_ar(request.form.get("total"))
        mov.total = total if total is not None else (mov.neto + mov.iva + mov.percepciones + mov.no_gravado)
        mov.cobrado = mov.tipo != "Ingreso" or bool(request.form.get("cobrado"))

        if not mov.total:
            flash("Poné el importe del movimiento.", "error")
        elif not mov.concepto and not mov.quien:
            flash("Escribí al menos el concepto o de quién es.", "error")
        else:
            if not id:
                db.session.add(mov)
            db.session.commit()
            flash("Movimiento guardado." if id else "Movimiento registrado.", "ok")
            return redirect(url_for(".movimientos", mes=mov.mes_imputacion))

    return render_template("contable/form.html", m=mov, tipos=TIPOS_MOVIMIENTO_CONTABLE,
                           clasificaciones=_clasificaciones(), comprobantes=COMPROBANTES,
                           meses=_meses_cargados())


@bp.route("/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    mov = db.get_or_404(MovimientoContable, id)
    if mov.automatico:
        flash("Este movimiento sale de una venta o de una compra: no se borra desde acá.", "error")
        return redirect(url_for(".movimientos", mes=mov.mes_imputacion))
    mes = mov.mes_imputacion
    db.session.delete(mov)
    db.session.commit()
    flash("Movimiento eliminado.", "ok")
    return redirect(url_for(".movimientos", mes=mes))


@bp.route("/<int:id>/cobrado", methods=["POST"])
def cobrado(id):
    """Marca un ingreso como cobrado (o lo vuelve a dejar pendiente)."""
    mov = db.get_or_404(MovimientoContable, id)
    mov.cobrado = request.form.get("cobrado") == "1"
    db.session.commit()
    return redirect(url_for(".movimientos", mes=mov.mes_imputacion) + f"#mov-{mov.id}")


# ─────────────────────────────────── Capital ────────────────────────────────


@bp.route("/capital")
def capital():
    aportes = AporteCapital.query.order_by(AporteCapital.fecha.desc(), AporteCapital.id.desc()).all()
    socios = Socio.query.order_by(Socio.orden, Socio.nombre).all()
    return render_template("contable/capital.html", aportes=aportes, socios=socios, hoy=date.today(),
                           tipos=TIPOS_CAPITAL,
                           total_pesos=sum(a.pesos_con_signo for a in aportes),
                           total_usd=sum(a.usd_con_signo for a in aportes))


@bp.route("/capital/nuevo", methods=["POST"])
def capital_nuevo():
    socio = db.session.get(Socio, request.form.get("socio_id", type=int) or 0)
    pesos = numero_ar(request.form.get("pesos"))
    cotizacion = numero_ar(request.form.get("cotizacion"))
    if socio is None or not pesos:
        flash("Elegí el socio y poné el monto.", "error")
    else:
        db.session.add(AporteCapital(
            fecha=_fecha("fecha", date.today()), socio=socio, pesos=pesos, cotizacion=cotizacion,
            tipo=request.form.get("tipo") if request.form.get("tipo") in TIPOS_CAPITAL else TIPOS_CAPITAL[0],
            notas=request.form.get("notas", "").strip() or None))
        db.session.commit()
        flash("Aporte registrado.", "ok")
    return redirect(url_for(".capital"))


@bp.route("/capital/<int:id>/eliminar", methods=["POST"])
def capital_eliminar(id):
    aporte = db.get_or_404(AporteCapital, id)
    db.session.delete(aporte)
    db.session.commit()
    flash("Aporte eliminado.", "ok")
    return redirect(url_for(".capital"))


# ───────────────────────────────── Cierre mensual ───────────────────────────


@bp.route("/cierres")
def cierres():
    """Todos los meses: los cerrados, con sus números, y el que está en curso."""
    cerrados = {c.mes: c for c in CierreMensual.query.order_by(CierreMensual.mes.desc()).all()}
    meses = sorted(set(_meses_cargados()) | set(cerrados), reverse=True)
    filas = []
    for mes in meses:
        c = cerrados.get(mes)
        filas.append({"mes": mes, "cierre": c, "numeros": calculo.numeros_del_mes(mes) if c is None else None})
    return render_template("contable/cierres.html", filas=filas)


@bp.route("/cierres/<mes>", methods=["GET", "POST"])
def cierre(mes):
    guardado = CierreMensual.query.filter_by(mes=mes).first()
    socios = Socio.query.order_by(Socio.orden, Socio.nombre).all()
    if not socios:
        flash("Cargá los socios en Configuración antes de cerrar un mes.", "error")
        return redirect(url_for("dashboard.configuracion") + "#socios")

    if request.method == "POST":
        accion = request.form.get("accion")
        if accion == "reabrir" and guardado is not None:
            calculo.limpiar_generado(guardado)
            db.session.delete(guardado)
            db.session.commit()
            flash(f"{mes_lindo(mes)} quedó abierto de nuevo: se borraron los sueldos y el colchón que había generado.", "ok")
            return redirect(url_for(".cierre", mes=mes))

        propuesta = calculo.calcular(mes, socios, numero_ar(request.form.get("colchon_objetivo")))
        c = guardado or CierreMensual(mes=mes)
        c.modo = "Manual" if request.form.get("modo") == "Manual" else "Automático"
        c.cotizacion = numero_ar(request.form.get("cotizacion"))
        c.fecha_cierre = _fecha("fecha_cierre", date.today())
        c.notas = request.form.get("notas", "").strip() or None
        c.ingresos, c.egresos = propuesta["ingresos"], propuesta["egresos"]
        c.colchon_entrante = propuesta["colchon_entrante"]
        if guardado is None:
            db.session.add(c)
        else:
            calculo.limpiar_generado(c)
            for fila in list(c.socios):
                db.session.delete(fila)
            c.socios = []
        db.session.flush()

        repago = ganancia = 0
        for fila in propuesta["reparto"]:
            s = fila["socio"]
            if c.modo == "Manual":
                sueldo = numero_ar(request.form.get(f"sueldo_{s.id}")) or 0
                suyo_repago = numero_ar(request.form.get(f"repago_{s.id}")) or 0
                suya_ganancia = numero_ar(request.form.get(f"ganancia_{s.id}")) or 0
            else:
                sueldo, suyo_repago, suya_ganancia = fila["sueldo"], fila["repago"], fila["ganancia"]
            repago += suyo_repago
            ganancia += suya_ganancia
            db.session.add(CierreSocio(cierre=c, socio=s, sueldo=sueldo, repago=suyo_repago, ganancia=suya_ganancia))
        c.repago, c.ganancia = repago, ganancia
        db.session.flush()

        disponible = max(c.resultado, 0)
        remanente = max(disponible - c.sueldos, 0)
        colchon = numero_ar(request.form.get("colchon")) if c.modo == "Manual" else propuesta["colchon"]
        c.colchon = colchon if colchon is not None else max(remanente - repago - ganancia, 0)

        if accion == "cerrar":
            c.estado = "Cerrado"
            calculo.generar_movimientos(c, calculo.mes_siguiente(mes))
            db.session.commit()
            flash(f"{mes_lindo(mes)} cerrado. Quedaron las liquidaciones de sueldo y el colchón "
                  f"de {(c.colchon or 0):,.0f} para el mes que viene.".replace(",", "."), "ok")
        else:
            c.estado = "Abierto"
            db.session.commit()
            flash("Borrador guardado.", "ok")
        return redirect(url_for(".cierre", mes=mes))

    objetivo = numero_ar(request.args.get("colchon_objetivo"))
    if objetivo is None and guardado is not None:
        objetivo = guardado.colchon
    propuesta = calculo.calcular(mes, socios, objetivo)
    return render_template("contable/cierre.html", mes=mes, c=guardado, p=propuesta, socios=socios,
                           hoy=date.today(), siguiente=calculo.mes_siguiente(mes))
