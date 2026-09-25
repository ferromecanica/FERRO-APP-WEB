"""La caja chica que maneja Iván.

El saldo no se carga a mano: es lo que entró en efectivo por las ventas menos
lo que salió. Lo que entró sale de las partes de cobro con destino Caja, así
que no hay que anotarlo dos veces ni se puede olvidar. Lo que sale se anota
(MovimientoCaja): gastos, depósitos al banco, retiros de un socio.

Un gasto de la caja deja además su egreso en la administración. La plata salió
de la caja, pero es un gasto del taller como cualquier otro y tiene que estar en
el resultado del mes. Los depósitos y los retiros no son gastos: la plata cambia
de lugar o se la lleva un socio, y eso se salda en el cierre.
"""
from datetime import date, timedelta

from ..extensions import db
from ..models import CAJA, MOVIMIENTOS_CAJA, MovimientoCaja, MovimientoContable, PagoVenta, Venta

CLASIFICACION_GASTO = "Gasto menor"


def _cobros_en_efectivo(hasta=None):
    """Las partes de cobro que entraron a la caja, ya acreditadas."""
    consulta = db.session.query(PagoVenta, Venta).join(Venta).filter(PagoVenta.destino == CAJA)
    if hasta:
        consulta = consulta.filter(PagoVenta.fecha_acreditacion <= hasta.isoformat())
    return consulta.all()


def entradas_por_ventas(hasta=None):
    """Cuánto efectivo entró por ventas (el efectivo no paga comisión: entra entero)."""
    return sum(p.neto for p, _ in _cobros_en_efectivo(hasta))


def saldo(hasta=None):
    """Lo que debería haber en la caja hoy."""
    anotados = MovimientoCaja.query
    if hasta:
        anotados = anotados.filter(MovimientoCaja.fecha <= hasta.isoformat())
    return entradas_por_ventas(hasta) + sum(m.contra_la_caja for m in anotados.all())


def movimientos(desde=None, hasta=None, inicial=0):
    """Lo que pasó por la caja en ese tramo, del más nuevo al más viejo.

    Mezcla las ventas en efectivo (que no se anotan) con lo anotado a mano, para
    que se lea como un extracto: cada línea dice cuánto quedaba después de ella,
    arrancando de lo que venía de antes.
    """
    filas = []
    for pago, venta in _cobros_en_efectivo(hasta):
        if desde and pago.fecha_acreditacion and pago.fecha_acreditacion < desde:
            continue
        quien = venta.cliente.nombre if venta.cliente else "Mostrador"
        filas.append({
            "fecha": pago.fecha_acreditacion or venta.fecha, "tipo": "Venta", "monto": pago.neto,
            "concepto": venta.detalle or "Venta", "quien": quien,
            "venta_id": venta.id, "movimiento": None,
        })
    anotados = MovimientoCaja.query
    if desde:
        anotados = anotados.filter(MovimientoCaja.fecha >= desde.isoformat())
    if hasta:
        anotados = anotados.filter(MovimientoCaja.fecha <= hasta.isoformat())
    for m in anotados.all():
        filas.append({
            "fecha": m.fecha, "tipo": m.tipo, "monto": m.contra_la_caja,
            "concepto": m.concepto or m.tipo, "quien": m.quien,
            "venta_id": None, "movimiento": m,
        })

    filas.sort(key=lambda f: (f["fecha"], f["movimiento"].id if f["movimiento"] else 0))
    corriendo = inicial
    for f in filas:
        corriendo += f["monto"]
        f["saldo"] = corriendo
    filas.reverse()  # el extracto se lee de lo último para atrás
    return filas


def anotar(tipo, monto, fecha=None, concepto=None, quien=None):
    """Anota un movimiento de la caja. Si es un gasto, deja también su egreso."""
    if tipo not in MOVIMIENTOS_CAJA:
        raise ValueError(f"No sé qué es «{tipo}» en la caja.")
    fecha = fecha or date.today()
    # Un gasto siempre resta; un ajuste se guarda como se escribió, porque puede
    # sumar (la apertura, plata que se repone) o restar (un depósito, un retiro)
    monto = abs(monto) if MOVIMIENTOS_CAJA[tipo]["gasto"] else monto
    m = MovimientoCaja(tipo=tipo, monto=monto, fecha=fecha, concepto=concepto, quien=quien)
    db.session.add(m)
    if m.es_gasto:
        m.movimiento = MovimientoContable(
            fecha=fecha, tipo="Egreso", mes_imputacion=MovimientoContable.mes_de(fecha),
            clasificacion=CLASIFICACION_GASTO, comprobante="S/C", quien=quien,
            concepto=f"{concepto or 'Gasto'} (caja chica)"[:300], total=abs(monto), cobrado=True,
        )
        db.session.add(m.movimiento)
    return m


def borrar(m):
    """Saca el movimiento y, si era un gasto, su egreso."""
    if m.movimiento is not None:
        db.session.delete(m.movimiento)
    db.session.delete(m)


def resumen(hasta=None):
    """Los números de arriba de la pantalla."""
    hasta = hasta or date.today()
    anotados = MovimientoCaja.query.filter(MovimientoCaja.fecha <= hasta.isoformat()).all()
    return {
        "saldo": saldo(hasta),
        "ventas": entradas_por_ventas(hasta),
        "gastos": sum(m.monto for m in anotados if m.es_gasto),
        "ajustes": sum(m.contra_la_caja for m in anotados if not m.es_gasto),
    }


def _primero_y_ultimo(mes):
    """Del '2026-09' al 1 y al 30 de septiembre."""
    anio, numero = (int(x) for x in mes.split("-"))
    primero = date(anio, numero, 1)
    ultimo = date(anio + (numero == 12), (numero % 12) + 1, 1) - timedelta(days=1)
    return primero, ultimo


def meses_con_movimiento():
    """Los meses que tienen algo, del más nuevo al más viejo. Siempre está el actual."""
    meses = {f"{m:%Y-%m}" for (m,) in db.session.query(MovimientoCaja.fecha).distinct()}
    meses |= {f"{p.fecha_acreditacion:%Y-%m}" for p, _ in _cobros_en_efectivo() if p.fecha_acreditacion}
    return sorted(meses | {f"{date.today():%Y-%m}"}, reverse=True)


def del_mes(mes):
    """El extracto de un mes: lo que venía de antes, lo que pasó y cómo quedó.

    Filtrar por mes es lo que evita que esto sea una sábana infinita. No hace
    falta borrar nada: el saldo necesita toda la historia para tener sentido.
    """
    primero, ultimo = _primero_y_ultimo(mes)
    inicial = saldo(primero - timedelta(days=1))
    filas = movimientos(desde=primero, hasta=ultimo, inicial=inicial)
    return {
        "mes": mes, "filas": filas, "inicial": inicial,
        "final": filas[0]["saldo"] if filas else inicial,
        "entro": sum(f["monto"] for f in filas if f["monto"] > 0),
        "salio": -sum(f["monto"] for f in filas if f["monto"] < 0),
    }
