"""Puente entre el taller y la administración.

Cada venta cobrada (de una OT o del mostrador) deja su ingreso en Movimientos,
atado a la venta. Así no hay que cargar dos veces lo mismo ni queda plata
facturada que no aparece en el cierre del mes.

Lo de antes de septiembre de 2026 vino importado de las dos apps de AppSheet por
separado, sin esa atadura: para eso está `ventas_sin_ingreso`, que compara mes a
mes y muestra lo que falta en vez de inventar el enganche.
"""
import re

from ..extensions import db
from ..models import CierreMensual, MovimientoContable, PagoVenta, Venta
from . import cobros

CLASIFICACION = "Ventas"


def ingresos_de(venta):
    """Los movimientos que ya tiene esa venta: uno por cada parte del cobro."""
    if venta.id is None:
        return []
    return MovimientoContable.query.filter_by(venta_id=venta.id).order_by(MovimientoContable.id).all()


def ingreso_de(venta):
    """El primer movimiento de la venta, para las pantallas que preguntan si está cargada."""
    movs = ingresos_de(venta)
    return movs[0] if movs else None


def _concepto(venta, parte):
    texto = venta.detalle or "Venta"
    if venta.ot_id and f"OT {venta.ot_id}" not in texto and f"OT:{venta.ot_id}" not in texto:
        texto = f"{texto}. OT:{venta.ot_id}"
    if len(cobros.partes_de(venta)) > 1:
        # Con el pago partido, cada ingreso dice de qué parte es
        texto = f"{texto} · {parte['nombre']}"
    if parte["bruto"] - parte["neto"] >= 1:
        # Queda anotado el bruto, así el número no parece un error
        texto = f"{texto} ({parte['nombre']}: se cobraron ${parte['bruto']:,.0f})".replace(",", ".")
    return texto[:300]


def registrar_venta(venta):
    """Deja en la administración un ingreso por cada parte del cobro.

    El cliente puede pagar una parte en efectivo y otra con tarjeta: el efectivo
    entra hoy y la tarjeta dentro de unos días, así que no pueden ser un solo
    ingreso sin mentir sobre cuándo está la plata.

    Las de $0 (sin cargo) no generan nada.
    """
    movs = ingresos_de(venta)
    if not venta.cobrado:
        for mov in movs:
            db.session.delete(mov)
        return None

    partes = [p for p in cobros.partes_de(venta) if p["neto"]]
    for sobrante in movs[len(partes):]:      # quedaron menos partes que antes
        db.session.delete(sobrante)
    creados = []
    for i, parte in enumerate(partes):
        mov = movs[i] if i < len(movs) else None
        if mov is None:
            mov = MovimientoContable(venta=venta)
            db.session.add(mov)
        # La plata cuenta el día que cae, no el día de la venta
        mov.fecha = parte["fecha"]
        mov.mes_imputacion = MovimientoContable.mes_de(mov.fecha)
        mov.tipo = "Ingreso"
        mov.clasificacion = CLASIFICACION
        mov.comprobante = venta.tipo_comprobante or "S/C"
        mov.quien = venta.cliente.nombre if venta.cliente else "Mostrador"
        mov.cuit = venta.cliente.cuit if venta.cliente else None
        mov.concepto = _concepto(venta, parte)
        mov.total = parte["neto"]  # con tarjeta, el neto que deposita
        mov.cobrado = True  # la venta se registra cuando se cobra
        creados.append(mov)
    return creados[0] if creados else None


def borrar_venta(venta):
    """Saca los ingresos cuando se anula la venta o se reabre la OT."""
    for mov in ingresos_de(venta):
        db.session.delete(mov)


# ───────────────────────── Control del mes ──────────────────────────


def _nombra_ot(movimiento, ot_id):
    """El concepto menciona esa OT ('OT:10088', 'OT 10088', 'OT #10088')."""
    if not ot_id:
        return False
    return any(int(n) == ot_id
               for n in re.findall(r"OT[:\s#]*(\d{4,6})", movimiento.concepto or "", re.I))


def _ventas_que_acreditan(mes):
    """Las ventas con plata cayendo en ese mes (con tarjeta, la acreditación manda).

    Una venta partida puede tener el efectivo en un mes y la tarjeta en el
    siguiente, así que se la busca por cualquiera de sus partes y después cada
    cuenta mira solo lo que entra en este mes.
    """
    desde, hasta = f"{mes}-01", f"{mes}-31"
    partidas = Venta.query.filter(Venta.pagos.any(db.and_(
        PagoVenta.fecha_acreditacion >= desde, PagoVenta.fecha_acreditacion <= hasta)))
    enteras = Venta.query.filter(~Venta.pagos.any()).filter(db.or_(
        db.and_(Venta.fecha_acreditacion.isnot(None),
                Venta.fecha_acreditacion >= desde, Venta.fecha_acreditacion <= hasta),
        db.and_(Venta.fecha_acreditacion.is_(None), Venta.fecha >= desde, Venta.fecha <= hasta),
    ))
    return sorted(set(partidas.all()) | set(enteras.all()), key=lambda v: (v.fecha, v.id))


def neto_del_mes(venta, mes):
    """De esa venta, cuánto entra en ese mes (una venta partida puede entrar en dos)."""
    return sum(p["neto"] for p in cobros.cobros_del_mes(venta, mes))


def conciliar(mes):
    """Cruza las ventas del taller con los ingresos de la administración.

    Lo de antes venía de dos apps separadas, así que además del enganche por id
    se busca la correspondencia como la haría uno a ojo: primero el emparejado
    a mano, después el número de OT escrito en el concepto y, si no, el importe.
    Cada ingreso tapa una sola venta, para que dos ventas del mismo monto no se
    tapen con uno solo.

    Devuelve cuatro cosas: las ventas que no están cargadas, los ingresos que no
    salen de una venta (cobros de deudas viejas, intereses, lo que sea), los
    pares que se corresponden pero por distinto importe, y las ventas que uno ya
    dio por revisadas y no se reclaman más.
    """
    ingresos = MovimientoContable.query.filter_by(mes_imputacion=mes, tipo="Ingreso").all()

    atadas = {m.venta_id for m in ingresos if m.venta_id}
    a_mano = {m.venta_conciliada_id: m for m in ingresos if m.venta_conciliada_id}
    libres = [m for m in ingresos if not m.venta_id and not m.venta_conciliada_id]
    pendientes = [v for v in _ventas_que_acreditan(mes)
                  if neto_del_mes(v, mes) and v.id not in atadas]

    sin_ot, distintos, revisadas = [], [], []
    for v in pendientes:
        # El emparejado a mano manda: uno ya dijo que ese ingreso es el de esta venta
        mov = a_mano.get(v.id) or next((m for m in libres if _nombra_ot(m, v.ot_id)), None)
        if mov is None:
            sin_ot.append(v)
            continue
        if mov in libres:
            libres.remove(mov)
        par = {"venta": v, "movimiento": mov, "diferencia": neto_del_mes(v, mes) - mov.total,
               "a_mano": mov.venta_conciliada_id == v.id}
        # Emparejarlo a mano o darlo por revisado es aceptar la diferencia. Los
        # emparejados van a la lista aunque coincidan, para poder deshacerlos
        if par["a_mano"] or v.revisada:
            revisadas.append(par)
        elif abs(par["diferencia"]) >= 1:
            distintos.append(par)

    faltan = []
    for v in sin_ot:
        mov = next((m for m in libres if abs(m.total - neto_del_mes(v, mes)) < 1), None)
        if mov is not None:
            libres.remove(mov)
        elif v.revisada:
            revisadas.append({"venta": v, "movimiento": None,
                              "diferencia": neto_del_mes(v, mes), "a_mano": False})
        else:
            faltan.append(v)
    return faltan, libres, distintos, revisadas


def ventas_sin_ingreso(mes):
    """Ventas del mes que no figuran en la administración."""
    return conciliar(mes)[0]


def control_del_mes(mes):
    """Compara lo facturado en Ventas contra lo cargado en la administración.

    Un mes ya cerrado no se controla: lo de antes vino importado de las dos apps
    de AppSheet por separado y quedó como quedó.

    La cuenta cierra siempre así:
        facturado − lo que falta cargar − lo desestimado
        − lo cargado por otro importe + lo que no sale de ventas = ingresos
    """
    cierre = CierreMensual.query.filter_by(mes=mes).first()
    if cierre is not None and cierre.cerrado:
        return None

    ventas = _ventas_que_acreditan(mes)
    delmes = [p for v in ventas for p in cobros.cobros_del_mes(v, mes)]
    facturado = sum(p["neto"] for p in delmes)
    tarjeta = sum(p["bruto"] - p["neto"] for p in delmes)
    ingresos = sum(m.total for m in MovimientoContable.query.filter_by(
        mes_imputacion=mes, tipo="Ingreso").all())
    faltantes, sin_venta, distintos, revisadas = conciliar(mes)
    # Las revisadas que no tienen ingreso salen del cuadre enteras; las que lo
    # tienen por otro importe aportan solo la diferencia, igual que las distintas
    sin_ingreso = [r for r in revisadas if r["movimiento"] is None]
    con_ingreso = [r for r in revisadas if r["movimiento"] is not None]
    return {
        "facturado": facturado,
        "tarjeta": tarjeta,
        "ingresos": ingresos,
        "diferencia": ingresos - facturado,
        "faltantes": faltantes,
        "falta": sum(neto_del_mes(v, mes) for v in faltantes),
        "sin_venta": sin_venta,
        "otros": sum(m.total for m in sin_venta),
        "distintos": distintos,
        "revisadas": revisadas,
        "desestimado": sum(r["diferencia"] for r in sin_ingreso),
        "ajuste": sum(d["diferencia"] for d in distintos) + sum(r["diferencia"] for r in con_ingreso),
    }
