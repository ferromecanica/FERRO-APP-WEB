"""El cierre mensual: la cuenta de cómo se reparte la plata del mes.

La lógica es la que venía de la app contable de AppSheet:

  resultado  = ingresos cobrados − egresos (sin sueldos ni capital) + colchón que entra
  sueldos    = cada socio cobra hasta su sueldo base, por orden, mientras alcance
  remanente  = lo que queda después de los sueldos
  del remanente: con deuda de capital → 40 % repago, 30 % ganancia, 30 % colchón
                 sin deuda            →  0 % repago, 50 % ganancia, 50 % colchón

El repago va proporcional a lo que puso cada socio (medido en dólares, que es
como se lleva la deuda) y la ganancia según la participación de cada uno.
"""
from ..extensions import db
from ..models import CierreMensual, MovimientoContable, Socio

PORCENTAJES = {
    "con_deuda": {"repago": 0.40, "ganancia": 0.30},
    "sin_deuda": {"repago": 0.00, "ganancia": 0.50},
}


def numeros_del_mes(mes):
    """Ingresos cobrados, egresos y colchón entrante de un mes."""
    movs = MovimientoContable.query.filter_by(mes_imputacion=mes).all()
    return {
        "ingresos": sum(m.total for m in movs if m.tipo == "Ingreso" and m.cobrado),
        "sin_cobrar": sum(m.total for m in movs if m.tipo == "Ingreso" and not m.cobrado),
        "egresos": sum(m.total for m in movs if m.tipo == "Egreso"
                       and m.comprobante != "Liquidación" and m.clasificacion != "Inversión de Capital"),
        "colchon_entrante": sum(m.total for m in movs if m.tipo == "Colchón"),
    }


def calcular(mes, socios=None):
    """La propuesta de cierre del mes, socio por socio. No toca nada."""
    socios = socios or Socio.query.order_by(Socio.orden, Socio.nombre).all()
    n = numeros_del_mes(mes)
    resultado = n["ingresos"] - n["egresos"] + n["colchon_entrante"]
    disponible = max(resultado, 0)

    # Los sueldos se pagan por orden: el primero cobra hasta su base, y así
    queda = disponible
    reparto = []
    for socio in socios:
        sueldo = min(queda, socio.sueldo_base or 0)
        queda -= sueldo
        reparto.append({"socio": socio, "sueldo": sueldo, "repago": 0.0, "ganancia": 0.0})

    remanente = max(queda, 0)
    deuda_usd = sum(s.capital_usd for s in socios)
    p = PORCENTAJES["con_deuda" if deuda_usd > 0 else "sin_deuda"]
    repago = round(remanente * p["repago"], 2) if remanente > 0 else 0.0
    ganancia = round(remanente * p["ganancia"], 2) if remanente > 0 else 0.0
    colchon = round(remanente - repago - ganancia, 2)

    # El repago sigue a lo que puso cada uno; la ganancia, a la participación
    for fila in reparto:
        parte = (fila["socio"].capital_usd / deuda_usd) if deuda_usd > 0 else 0
        fila["repago"] = round(repago * parte, 2)
        fila["ganancia"] = round(ganancia * (fila["socio"].participacion or 0), 2)

    return dict(n, mes=mes, resultado=resultado, disponible=disponible, sueldos=disponible - queda,
                remanente=remanente, deuda_usd=deuda_usd, repago=repago, ganancia=ganancia,
                colchon=colchon, reparto=reparto, porcentajes=p)


def limpiar_generado(cierre):
    """Borra lo que había generado un cierre anterior (sueldos, devoluciones, colchón)."""
    for mov in list(cierre.movimientos):
        db.session.delete(mov)
    for devolucion in list(cierre.devoluciones):
        db.session.delete(devolucion)
    cierre.movimientos, cierre.devoluciones = [], []


def generar_movimientos(cierre, mes_siguiente):
    """Después de cerrar: liquidaciones de sueldo, devoluciones de capital y el colchón."""
    from datetime import date

    from ..models import AporteCapital

    fecha = cierre.fecha_cierre or date.today()
    for fila in cierre.socios:
        if fila.sueldo:
            db.session.add(MovimientoContable(
                fecha=fecha, tipo="Egreso", mes_imputacion=cierre.mes, clasificacion="Sueldos",
                comprobante="Liquidación", quien=fila.socio.nombre,
                concepto=f"Sueldo de {fila.socio.nombre}", total=fila.sueldo, cierre=cierre))
        if fila.repago:
            db.session.add(AporteCapital(
                fecha=fecha, socio=fila.socio, tipo="Devolución de Capital", pesos=fila.repago,
                cotizacion=cierre.cotizacion, notas=f"Repago del cierre de {cierre.mes}", cierre=cierre))
            db.session.add(MovimientoContable(
                fecha=fecha, tipo="Egreso", mes_imputacion=cierre.mes, clasificacion="Inversión de Capital",
                comprobante="S/C", quien=fila.socio.nombre,
                concepto=f"Repago de capital a {fila.socio.nombre}", total=fila.repago, cierre=cierre))
        if fila.ganancia:
            db.session.add(MovimientoContable(
                fecha=fecha, tipo="Egreso", mes_imputacion=cierre.mes, clasificacion="Sueldos",
                comprobante="Liquidación", quien=fila.socio.nombre,
                concepto=f"Ganancia de {fila.socio.nombre}", total=fila.ganancia, cierre=cierre))
    if cierre.colchon:
        db.session.add(MovimientoContable(
            fecha=fecha, tipo="Colchón", mes_imputacion=mes_siguiente, clasificacion=None,
            comprobante="S/C", concepto=f"Colchón que viene de {cierre.mes}",
            total=cierre.colchon, cierre=cierre))


def mes_siguiente(mes):
    anio, numero = (int(x) for x in mes.split("-"))
    return f"{anio + 1}-01" if numero == 12 else f"{anio}-{numero + 1:02d}"
