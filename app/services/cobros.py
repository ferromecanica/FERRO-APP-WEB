"""Cómo se cobra una venta: con una forma de pago o con dos.

Muchos clientes dejan una parte en efectivo y el resto con tarjeta. Cada parte
tiene su comisión y su fecha de acreditación, así que se guardan por separado
(PagoVenta) y cada una deja su propio ingreso en la administración.

Las tres columnas viejas de Venta —bruto_cobrado, neto_acreditado y
fecha_acreditacion— se siguen llenando con el resumen de las partes: son las que
leen los listados, Performance y el importador, y así no hay que tocarlas. La
fecha del resumen es la de la última parte en entrar, que es cuando la venta
terminó de cobrarse.
"""
from ..extensions import db
from ..models import CondicionPago, PagoVenta
from ..validaciones import numero_ar

MAX_PARTES = 2  # con dos alcanza: "una parte en efectivo y el resto con tarjeta"


def leer_del_formulario(form, prefijo="pago", sugerido=None):
    """Saca las partes del cobro de un formulario y avisa qué está mal.

    Espera pago_condicion_1 / pago_total_1, pago_condicion_2 / pago_total_2…
    La segunda parte es opcional: si no tiene importe, no existe.

    Con `sugerido`, una sola forma de pago sin importe escrito cobra eso: en el
    mostrador el total de lo que se lleva ya está a la vista y no tiene sentido
    obligar a copiarlo.
    """
    crudas, errores = [], []
    for n in range(1, MAX_PARTES + 1):
        condicion = db.session.get(CondicionPago, form.get(f"{prefijo}_condicion_{n}", type=int) or 0)
        bruto = numero_ar(form.get(f"{prefijo}_total_{n}"))
        if condicion is not None or bruto is not None:
            crudas.append((n, condicion, bruto))

    if len(crudas) == 1 and crudas[0][2] is None and sugerido:
        crudas = [(crudas[0][0], crudas[0][1], sugerido)]

    partes = []
    for n, condicion, bruto in crudas:
        if condicion is None:
            errores.append(f"Elegí la forma de pago {'de la segunda parte' if n > 1 else ''}".strip() + ".")
        elif bruto is None or bruto <= 0:
            errores.append(f"Poné cuánto se cobró con {condicion.nombre}.")
        else:
            partes.append((condicion, bruto))
    if not partes and not errores:
        errores.append("Elegí la forma de pago y escribí el total cobrado.")
    return partes, errores


def anotar(venta, partes, fecha):
    """Deja en la venta las partes del cobro y el resumen que leen las demás pantallas.

    `partes` es una lista de (condición, lo que pagó el cliente en esa parte).
    """
    for viejo in list(venta.pagos):
        db.session.delete(viejo)
    venta.pagos = []
    for orden, (condicion, bruto) in enumerate(partes, start=1):
        venta.pagos.append(PagoVenta(
            condicion=condicion, orden=orden, bruto=bruto,
            neto=condicion.neto(bruto), fecha_acreditacion=condicion.acredita(fecha),
        ))

    venta.condicion = partes[0][0] if partes else None
    venta.metodo_pago = " + ".join(c.nombre for c, _ in partes) or None
    venta.bruto_cobrado = sum(b for _, b in partes)
    venta.neto_acreditado = sum(c.neto(b) for c, b in partes)
    # La venta termina de cobrarse cuando entra la última parte
    venta.fecha_acreditacion = max((p.fecha_acreditacion for p in venta.pagos if p.fecha_acreditacion),
                                   default=None)
    return venta


def partes_de(venta):
    """Las partes del cobro, siempre con la misma forma.

    Las ventas viejas (las importadas y las de antes de este cambio) no tienen
    partes: cuentan como una sola, que es lo que eran.
    """
    if venta.pagos:
        return [{"neto": p.neto, "bruto": p.bruto, "nombre": p.nombre,
                 "fecha": p.fecha_acreditacion or venta.fecha} for p in venta.pagos]
    return [{"neto": venta.cobrado, "bruto": venta.bruto_cobrado or venta.total,
             "nombre": venta.metodo_pago or "", "fecha": venta.fecha_acreditacion or venta.fecha}]


def cobros_del_mes(venta, mes):
    """Las partes de esta venta cuya plata cae en ese mes.

    Una venta partida puede tener el efectivo en un mes y la tarjeta en el
    siguiente: para el cierre, cada parte cuenta el mes en que entra.
    """
    return [p for p in partes_de(venta) if f"{p['fecha']:%Y-%m}" == mes]
