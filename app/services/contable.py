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
from ..models import CierreMensual, MovimientoContable, Venta

CLASIFICACION = "Ventas"


def ingreso_de(venta):
    """El movimiento que ya tiene esa venta, si lo tiene."""
    if venta.id is None:
        return None
    return MovimientoContable.query.filter_by(venta_id=venta.id).first()


def _concepto(venta):
    texto = venta.detalle or "Venta"
    if venta.ot_id and f"OT {venta.ot_id}" not in texto and f"OT:{venta.ot_id}" not in texto:
        texto = f"{texto}. OT:{venta.ot_id}"
    if venta.costo_tarjeta:
        # Queda anotado el bruto, así el número no parece un error
        texto = f"{texto} ({venta.metodo_pago}: se cobraron ${venta.bruto_cobrado:,.0f})".replace(",", ".")
    return texto[:300]


def registrar_venta(venta):
    """Crea o actualiza el ingreso de una venta. Las de $0 (sin cargo) no generan nada."""
    mov = ingreso_de(venta)
    if not venta.cobrado:
        if mov is not None:
            db.session.delete(mov)
        return None

    if mov is None:
        mov = MovimientoContable(venta=venta)
        db.session.add(mov)
    # La plata cuenta el día que cae en el banco, no el día de la venta
    mov.fecha = venta.fecha_acreditacion or venta.fecha
    mov.mes_imputacion = MovimientoContable.mes_de(mov.fecha)
    mov.tipo = "Ingreso"
    mov.clasificacion = CLASIFICACION
    mov.comprobante = venta.tipo_comprobante or "S/C"
    mov.quien = venta.cliente.nombre if venta.cliente else "Mostrador"
    mov.cuit = venta.cliente.cuit if venta.cliente else None
    mov.concepto = _concepto(venta)
    mov.total = venta.cobrado  # con tarjeta, el neto que deposita
    mov.cobrado = True  # la venta se registra cuando se cobra
    return mov


def borrar_venta(venta):
    """Saca el ingreso cuando se anula la venta o se reabre la OT."""
    mov = ingreso_de(venta)
    if mov is not None:
        db.session.delete(mov)


# ───────────────────────── Control del mes ──────────────────────────


def _nombra_ot(movimiento, ot_id):
    """El concepto menciona esa OT ('OT:10088', 'OT 10088', 'OT #10088')."""
    if not ot_id:
        return False
    return any(int(n) == ot_id
               for n in re.findall(r"OT[:\s#]*(\d{4,6})", movimiento.concepto or "", re.I))


def _ventas_que_acreditan(mes):
    """Las ventas cuya plata cae en ese mes (con tarjeta, la acreditación manda)."""
    desde, hasta = f"{mes}-01", f"{mes}-31"
    porfecha = Venta.query.filter(db.or_(
        db.and_(Venta.fecha_acreditacion.isnot(None),
                Venta.fecha_acreditacion >= desde, Venta.fecha_acreditacion <= hasta),
        db.and_(Venta.fecha_acreditacion.is_(None), Venta.fecha >= desde, Venta.fecha <= hasta),
    )).order_by(Venta.fecha).all()
    return porfecha


def conciliar(mes):
    """Cruza las ventas del taller con los ingresos de la administración.

    Lo de antes venía de dos apps separadas, así que además del enganche por id
    se busca la correspondencia como la haría uno a ojo: por el número de OT
    escrito en el concepto y, si no, por importe. Cada ingreso tapa una sola
    venta, para que dos ventas del mismo monto no se tapen con uno solo.

    Devuelve tres cosas: las ventas que no están cargadas, los ingresos que no
    salen de una venta (cobros de deudas viejas, intereses, lo que sea) y los
    pares que se corresponden pero por distinto importe.
    """
    ingresos = MovimientoContable.query.filter_by(mes_imputacion=mes, tipo="Ingreso").all()

    atadas = {m.venta_id for m in ingresos if m.venta_id}
    libres = [m for m in ingresos if not m.venta_id]
    pendientes = [v for v in _ventas_que_acreditan(mes) if v.cobrado and v.id not in atadas]

    sin_ot, distintos = [], []
    for v in pendientes:
        mov = next((m for m in libres if _nombra_ot(m, v.ot_id)), None)
        if mov is None:
            sin_ot.append(v)
            continue
        libres.remove(mov)
        if abs(mov.total - v.cobrado) >= 1:
            distintos.append({"venta": v, "movimiento": mov, "diferencia": v.cobrado - mov.total})

    faltan = []
    for v in sin_ot:
        mov = next((m for m in libres if abs(m.total - v.cobrado) < 1), None)
        if mov is not None:
            libres.remove(mov)
        else:
            faltan.append(v)
    return faltan, libres, distintos


def ventas_sin_ingreso(mes):
    """Ventas del mes que no figuran en la administración."""
    return conciliar(mes)[0]


def control_del_mes(mes):
    """Compara lo facturado en Ventas contra lo cargado en la administración.

    Un mes ya cerrado no se controla: lo de antes vino importado de las dos apps
    de AppSheet por separado y quedó como quedó.

    La cuenta cierra siempre así:
        facturado − costo de tarjeta − lo que falta cargar
        − lo cargado por otro importe + lo que no sale de ventas = ingresos
    """
    cierre = CierreMensual.query.filter_by(mes=mes).first()
    if cierre is not None and cierre.cerrado:
        return None

    ventas = _ventas_que_acreditan(mes)
    facturado = sum(v.cobrado for v in ventas)
    tarjeta = sum(v.costo_tarjeta for v in ventas)
    ingresos = sum(m.total for m in MovimientoContable.query.filter_by(
        mes_imputacion=mes, tipo="Ingreso").all())
    faltantes, sin_venta, distintos = conciliar(mes)
    return {
        "facturado": facturado,
        "tarjeta": tarjeta,
        "ingresos": ingresos,
        "diferencia": ingresos - facturado,
        "faltantes": faltantes,
        "falta": sum(v.cobrado for v in faltantes),
        "sin_venta": sin_venta,
        "otros": sum(m.total for m in sin_venta),
        "distintos": distintos,
        "ajuste": sum(d["diferencia"] for d in distintos),
    }
