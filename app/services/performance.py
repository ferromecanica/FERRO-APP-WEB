"""Los números del taller para la pantalla de Performance.

Todo sale de lo que ya se carga: las ventas, los movimientos de la
administración y el stock. Nada que haya que cargar aparte.
"""
import math
from datetime import date

from ..extensions import db
from ..models import ESTADOS_OT_ABIERTA, MovimientoContable, OrdenTrabajo, Repuesto, Venta

MESES_COMPARA = 6  # cuántos meses miramos para atrás

# Lo que no es gasto de funcionamiento: se cuenta aparte para no ensuciar la torta
FUERA_DE_LA_TORTA = ("Liquidación",)
CLASIF_FUERA = ("Inversión de Capital",)

COLORES = ["#0d9488", "#f59e0b", "#3b82f6", "#a855f7", "#ef4444", "#14b8a6", "#64748b"]


def _mes_de(fecha):
    return f"{fecha:%Y-%m}"


def _restar_meses(fecha, n):
    mes, anio = fecha.month - n, fecha.year
    while mes <= 0:
        mes += 12
        anio -= 1
    return date(anio, mes, 1)


def _ultimos_meses(hoy, cuantos):
    """Del más viejo al más nuevo, incluyendo el mes en curso."""
    return [_restar_meses(hoy, n) for n in range(cuantos - 1, -1, -1)]


# ──────────────────────────── Relojes ───────────────────────────────

LARGO_ARCO = math.pi * 56  # el arco del reloj, de punta a punta


def tono(contra_promedio):
    """Verde si el mes viene bien; amarillo por debajo del 25 %, rojo del 40 %."""
    if contra_promedio <= -40:
        return "tono-malo"
    if contra_promedio <= -25:
        return "tono-aviso"
    return ""


def reloj(valor, tope, marca=None):
    """Cuánto se pinta del arco, y dónde va la rayita de referencia."""
    tope = tope or 1
    parte = min(max(valor / tope, 0), 1)
    datos = {"largo": round(parte * LARGO_ARCO, 1), "porcentaje": parte * 100}
    if marca:
        angulo = math.pi * (1 - min(max(marca / tope, 0), 1))
        datos["marca"] = {
            "x1": round(70 + 47 * math.cos(angulo), 1), "y1": round(70 - 47 * math.sin(angulo), 1),
            "x2": round(70 + 65 * math.cos(angulo), 1), "y2": round(70 - 65 * math.sin(angulo), 1),
        }
    return datos


# ─────────────────────────── Facturación ────────────────────────────


def facturacion_al_dia(hoy):
    """Cuánto se facturó en cada mes hasta el mismo día del mes.

    Comparar el 20 de septiembre contra meses enteros no dice nada: se compara
    contra los primeros 20 días de cada mes.
    """
    filas = []
    for primero in _ultimos_meses(hoy, MESES_COMPARA):
        hasta = f"{primero:%Y-%m}-{min(hoy.day, 31):02d}"
        ventas = Venta.query.filter(Venta.fecha >= primero.isoformat(), Venta.fecha <= hasta).all()
        filas.append({"mes": primero, "clave": _mes_de(primero),
                      "total": sum(v.cobrado for v in ventas), "ventas": len(ventas),
                      "actual": _mes_de(primero) == _mes_de(hoy)})
    return filas


def _proyeccion(hoy, facturado):
    """A este ritmo, cómo termina el mes."""
    dias_del_mes = (_restar_meses(hoy.replace(day=1), -1) - hoy.replace(day=1)).days
    if hoy.day <= 0:
        return facturado
    return facturado / hoy.day * dias_del_mes


# ───────────────────────────── Margen ───────────────────────────────


def margen_del_mes(hoy):
    """Lo facturado menos lo que costaron los repuestos y la compra."""
    desde, hasta = hoy.replace(day=1), hoy
    ventas = Venta.query.filter(Venta.fecha >= desde.isoformat(), Venta.fecha <= hasta.isoformat()).all()
    total = sum(v.cobrado for v in ventas)
    costo = sum(v.costo_total for v in ventas)
    sin_costo = sum(1 for v in ventas for i in v.items if not i.costo_unitario)
    return {"total": total, "costo": costo, "ganancia": total - costo,
            "porcentaje": (total - costo) / total * 100 if total else 0,
            "sin_costo": sin_costo, "ventas": len(ventas)}


# ─────────────────────────── Administración ─────────────────────────


def _egresos_del_mes(mes):
    return [m for m in MovimientoContable.query.filter_by(mes_imputacion=mes, tipo="Egreso").all()
            if m.comprobante not in FUERA_DE_LA_TORTA and m.clasificacion not in CLASIF_FUERA]


def resultado_del_mes(mes):
    """El resultado operativo, con el mismo criterio que Movimientos y el cierre.

    El colchón que viene del mes anterior es plata disponible: sin él, el número
    no coincide con el del cierre mensual.
    """
    movs = MovimientoContable.query.filter_by(mes_imputacion=mes).all()
    ingresos = sum(m.total for m in movs if m.tipo == "Ingreso" and m.cobrado)
    egresos = sum(m.total for m in movs if m.tipo == "Egreso"
                  and m.comprobante not in FUERA_DE_LA_TORTA and m.clasificacion not in CLASIF_FUERA)
    colchon = sum(m.total for m in movs if m.tipo == "Colchón")
    sueldos = sum(m.total for m in movs if m.comprobante == "Liquidación")
    return {"ingresos": ingresos, "egresos": egresos, "colchon": colchon, "sueldos": sueldos,
            "resultado": ingresos - egresos + colchon}


def _torta(pares):
    """Arma los pedazos del gráfico: cada uno con su porcentaje y su vuelta."""
    total = sum(v for _, v in pares) or 1
    pedazos, vuelta = [], 0
    for i, (nombre, valor) in enumerate(pares):
        porcentaje = valor / total * 100
        pedazos.append({"nombre": nombre, "valor": valor, "porcentaje": porcentaje,
                        "color": COLORES[i % len(COLORES)],
                        "largo": round(porcentaje, 2), "resto": round(100 - porcentaje, 2),
                        "offset": round(25 - vuelta, 2)})
        vuelta += porcentaje
    return {"pedazos": pedazos, "total": sum(v for _, v in pares)}


def egresos_por_clasificacion(hoy, meses=3):
    junta = {}
    for primero in _ultimos_meses(hoy, meses):
        for m in _egresos_del_mes(_mes_de(primero)):
            junta[m.clasificacion or "Sin clasificar"] = junta.get(m.clasificacion or "Sin clasificar", 0) + m.total
    return _torta(sorted(junta.items(), key=lambda x: -x[1]))


def de_donde_sale(hoy, meses=3):
    """La facturación abierta por tipo de trabajo."""
    junta = {"Servicio": 0, "Otros trabajos": 0, "Mostrador": 0}
    desde = _ultimos_meses(hoy, meses)[0]
    for v in Venta.query.filter(Venta.fecha >= desde.isoformat()).all():
        if v.ot is None:
            junta["Mostrador"] += v.cobrado
        elif v.ot.clasificacion_cierre == "Servicio":
            junta["Servicio"] += v.cobrado
        else:
            junta["Otros trabajos"] += v.cobrado
    return _torta([(k, v) for k, v in sorted(junta.items(), key=lambda x: -x[1]) if v])


def top_clientes(hoy, meses=6, cuantos=5):
    desde = _ultimos_meses(hoy, meses)[0]
    junta = {}
    for v in Venta.query.filter(Venta.fecha >= desde.isoformat()).all():
        nombre = v.cliente.nombre if v.cliente else "Mostrador"
        junta[nombre] = junta.get(nombre, 0) + v.cobrado
    ordenados = sorted(junta.items(), key=lambda x: -x[1])
    total = sum(v for _, v in ordenados) or 1
    return [{"nombre": n, "total": t, "porcentaje": t / total * 100} for n, t in ordenados[:cuantos]]


def top_proveedores(hoy, meses=6, cuantos=5):
    junta = {}
    for primero in _ultimos_meses(hoy, meses):
        for m in _egresos_del_mes(_mes_de(primero)):
            if m.quien:
                junta[m.quien] = junta.get(m.quien, 0) + m.total
    ordenados = sorted(junta.items(), key=lambda x: -x[1])
    total = sum(v for _, v in ordenados) or 1
    return [{"nombre": n, "total": t, "porcentaje": t / total * 100} for n, t in ordenados[:cuantos]]


# ───────────────────────────── Stock ────────────────────────────────


def valor_del_stock():
    repuestos = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).all()
    con_stock = [r for r in repuestos if (r.stock_actual or 0) > 0]
    costo = sum((r.stock_actual or 0) * (r.precio_costo or 0) for r in con_stock)
    venta = sum((r.stock_actual or 0) * (r.precio_venta or 0) for r in con_stock)
    bajo_minimo = [r for r in repuestos if r.stock_minimo and (r.stock_actual or 0) <= r.stock_minimo]
    caros = sorted(con_stock, key=lambda r: -((r.stock_actual or 0) * (r.precio_costo or 0)))[:5]
    return {"costo": costo, "venta": venta, "ganancia": venta - costo,
            "articulos": len(con_stock), "bajo_minimo": bajo_minimo,
            "caros": [{"repuesto": r, "plata": (r.stock_actual or 0) * (r.precio_costo or 0)} for r in caros]}


def en_camino(hoy):
    """Ventas con tarjeta que todavía no se acreditaron."""
    ventas = Venta.query.filter(Venta.fecha_acreditacion > hoy).order_by(Venta.fecha_acreditacion).all()
    return {"ventas": ventas,
            "total": sum(v.cobrado for v in ventas),
            "bruto": sum(v.bruto_cobrado or v.total for v in ventas)}


# ───────────────────────────── Taller ───────────────────────────────


def taller(hoy):
    abiertas = OrdenTrabajo.query.filter(OrdenTrabajo.estado.in_(ESTADOS_OT_ABIERTA)).count()
    por_cobrar = [o for o in OrdenTrabajo.query.filter_by(estado="Finalizada").all() if o.por_cobrar]
    desde = _ultimos_meses(hoy, 1)[0]
    cerradas = OrdenTrabajo.query.filter(OrdenTrabajo.fecha_fin >= desde.isoformat()).all()
    sin_cargo = [o for o in cerradas if o.sin_cargo]
    demoras = [(o.fecha_fin - o.fecha_ingreso).days for o in cerradas if o.fecha_fin and o.fecha_ingreso]
    return {"abiertas": abiertas, "por_cobrar": len(por_cobrar),
            "cerradas_mes": len(cerradas), "sin_cargo": len(sin_cargo),
            "demora": sum(demoras) / len(demoras) if demoras else 0}


# ───────────────────────────── Todo junto ───────────────────────────


def tablero(hoy=None):
    hoy = hoy or date.today()
    comparativa = facturacion_al_dia(hoy)
    actual = comparativa[-1]
    anteriores = [f["total"] for f in comparativa[:-1] if f["total"]]
    promedio = sum(anteriores) / len(anteriores) if anteriores else 0
    contra = (actual["total"] / promedio - 1) * 100 if promedio else 0
    tope = max([f["total"] for f in comparativa] + [1])
    for f in comparativa:
        f["alto"] = f["total"] / tope * 100

    margen = margen_del_mes(hoy)
    plata = resultado_del_mes(_mes_de(hoy))
    stock = valor_del_stock()
    return {
        "hoy": hoy,
        "relojes": {
            "facturacion": reloj(actual["total"], max(actual["total"], promedio) * 1.25 or 1, promedio),
            "margen": reloj(margen["porcentaje"], 100),
            "resultado": reloj(max(plata["resultado"], 0), (plata["ingresos"] + plata["colchon"]) or 1),
            "stock": reloj(stock["costo"], stock["venta"] or 1),
        },
        "mes": _mes_de(hoy),
        "comparativa": comparativa,
        "facturado": actual["total"],
        "promedio": promedio,
        "contra_promedio": contra,
        "tono": tono(contra) if promedio else "",
        "proyeccion": _proyeccion(hoy, actual["total"]),
        "margen": margen,
        "plata": plata,
        "egresos": egresos_por_clasificacion(hoy),
        "origen": de_donde_sale(hoy),
        "clientes": top_clientes(hoy),
        "proveedores": top_proveedores(hoy),
        "stock": stock,
        "en_camino": en_camino(hoy),
        "taller": taller(hoy),
    }
