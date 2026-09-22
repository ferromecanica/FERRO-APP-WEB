"""Importa la app contable de AppSheet (Admin Taller.xlsx) al módulo Administración.

Uso:  python scripts/importar_contable.py <ruta al .xlsx>

Trae socios, movimientos, aportes de capital y los cierres ya hechos. Se puede
correr varias veces: cada registro se reconoce por el ID que tenía en AppSheet.
Hace una copia de la base antes de tocar nada.
"""
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import openpyxl  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    AporteCapital, CierreMensual, CierreSocio, MovimientoContable, Socio,
)
from app.services.backup import hacer_copia  # noqa: E402

MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
         "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}


def filas(libro, hoja):
    it = libro[hoja].iter_rows(values_only=True)
    encabezado = next(it)
    return [dict(zip(encabezado, r)) for r in it if r and any(v is not None for v in r)]


def texto(valor):
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip() or None


def numero(valor):
    if valor is None or valor == "":
        return None
    try:
        return float(str(valor).replace("$", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def fecha_de(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valor).strip(), formato).date()
        except (ValueError, TypeError):
            continue
    return None


def mes_de(valor, fecha=None):
    """'AGOSTO-2026' → '2026-08'. Si no se entiende, usa el mes de la fecha."""
    t = (texto(valor) or "").upper().replace(" ", "")
    if "-" in t:
        nombre, _, anio = t.partition("-")
        if nombre in MESES and anio.isdigit():
            return f"{int(anio)}-{MESES[nombre]:02d}"
    return f"{fecha:%Y-%m}" if fecha else None


def importar_socios(libro):
    """Los socios, en el orden en que cobran (el primero de la hoja, primero)."""
    nuevos = 0
    for i, s in enumerate(filas(libro, "Socios_Config"), start=1):
        nombre = texto(s.get("ID_Socio"))
        if not nombre:
            continue
        socio = Socio.query.filter(db.func.lower(Socio.nombre) == nombre.lower()).first()
        if socio is None:
            socio = Socio(nombre=nombre, orden=i)
            db.session.add(socio)
            nuevos += 1
        socio.rol = texto(s.get("Rol"))
        socio.sueldo_base = numero(s.get("Sueldo_Base")) or 0
        socio.alias = texto(s.get("CBU_Alias"))
        if socio.participacion is None:
            socio.participacion = 0.5
    db.session.flush()
    return nuevos


def importar_movimientos(libro, ventas=None):
    """Los movimientos de la contable.

    Con `ventas` ({ID_Venta de AppSheet: venta}) trae solo los que salen de esas
    ventas y los deja atados a ellas, como los que genera Ferro al cobrar.
    """
    nuevos = actualizados = 0
    for m in filas(libro, "Movimientos"):
        origen = texto(m.get("ID_Movimiento"))
        fecha = fecha_de(m.get("Fecha"))
        total = numero(m.get("Importe_Total"))
        if not origen or not fecha or total is None:
            continue
        venta = (ventas or {}).get(texto(m.get("ID_Origen_Taller")))
        if ventas is not None and venta is None:
            continue
        mov = MovimientoContable.query.filter_by(origen=origen).first()
        if mov is None:
            mov = MovimientoContable(origen=origen)
            db.session.add(mov)
            nuevos += 1
        else:
            actualizados += 1
        tipo = texto(m.get("Tipo")) or "Egreso"
        mov.fecha, mov.tipo, mov.total = fecha, tipo, total
        mov.mes_imputacion = mes_de(m.get("Mes_Imputacion"), fecha)
        mov.clasificacion = texto(m.get("Clasificación"))
        mov.comprobante = texto(m.get("Comprobante")) or "S/C"
        mov.nro_comprobante = texto(m.get("Numero_Comprobante"))
        mov.quien = texto(m.get("Proveedor_Cliente"))
        mov.cuit = texto(m.get("CUIT"))
        mov.concepto = texto(m.get("Concepto"))
        mov.neto = numero(m.get("Importe_Neto")) or 0
        mov.iva = numero(m.get("IVA_Monto")) or 0
        mov.percepciones = numero(m.get("Percepciones")) or 0
        mov.no_gravado = numero(m.get("Importe_No_Gravado")) or 0
        mov.cobrado = tipo != "Ingreso" or texto(m.get("Estado_Cobro")) == "Cobrado"
        if venta is not None:
            mov.venta = venta
    return nuevos, actualizados


def importar_capital(libro):
    nuevos = actualizados = 0
    for a in filas(libro, "Capital_Cuenta_Corriente"):
        origen = texto(a.get("ID_Mov_Cap"))
        fecha = fecha_de(a.get("Fecha"))
        pesos = numero(a.get("Monto_Original_Pesos"))
        nombre = texto(a.get("ID_Socio"))
        socio = Socio.query.filter(db.func.lower(Socio.nombre) == (nombre or "").lower()).first()
        if not origen or not fecha or pesos is None or socio is None:
            continue
        aporte = AporteCapital.query.filter_by(origen=origen).first()
        if aporte is None:
            aporte = AporteCapital(origen=origen)
            db.session.add(aporte)
            nuevos += 1
        else:
            actualizados += 1
        aporte.fecha, aporte.socio, aporte.pesos = fecha, socio, pesos
        aporte.tipo = texto(a.get("Tipo_Movimiento")) or "Aporte de Capital"
        aporte.cotizacion = numero(a.get("Cotizacion_Dolar"))
        aporte.notas = texto(a.get("Notas"))
    return nuevos, actualizados


def importar_cierres(libro):
    """Los cierres ya hechos, con lo que cobró cada socio. Quedan como Cerrados."""
    nuevos = 0
    socios = {s.nombre.lower(): s for s in Socio.query.all()}
    for c in filas(libro, "Cierre_Mensual"):
        mes = mes_de(c.get("ID_Cierre"), fecha_de(c.get("Fecha_Cierre")))
        if not mes:
            continue
        cierre = CierreMensual.query.filter_by(mes=mes).first()
        if cierre is None:
            cierre = CierreMensual(mes=mes)
            db.session.add(cierre)
            nuevos += 1
        cierre.fecha_cierre = fecha_de(c.get("Fecha_Cierre"))
        cierre.cotizacion = numero(c.get("Cotizacion_Dolar_Dia"))
        cierre.estado = "Cerrado" if texto(c.get("Estado")) == "Cerrado" else "Abierto"
        cierre.modo = "Manual" if texto(c.get("Modo_Calculo")) == "Manual" else "Automático"
        cierre.ingresos = numero(c.get("Total_Facturado")) or 0
        cierre.egresos = numero(c.get("Total_Gastos")) or 0
        resultado = numero(c.get("Resultado_Operativo")) or 0
        # el colchón que entró no está en la hoja: sale de la cuenta
        cierre.colchon_entrante = round(resultado - cierre.ingresos + cierre.egresos, 2)
        cierre.colchon = numero(c.get("Monto_Colchon")) or 0
        db.session.flush()
        for fila in list(cierre.socios):
            db.session.delete(fila)
        repago_total = ganancia_total = 0
        for nombre, socio in socios.items():
            clave = nombre.capitalize().replace("á", "a").replace("í", "i")  # Sueldo_Ivan_Aplicado
            sueldo = numero(c.get(f"Sueldo_{clave}_Aplicado")) or 0
            repago = numero(c.get(f"Repago_Final_{clave}")) or 0
            if sueldo or repago:
                db.session.add(CierreSocio(cierre=cierre, socio=socio, sueldo=sueldo, repago=repago, ganancia=0))
                repago_total += repago
        cierre.repago, cierre.ganancia = repago_total, ganancia_total
    return nuevos


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    libro = openpyxl.load_workbook(sys.argv[1], data_only=True, read_only=True)
    app = create_app()
    with app.app_context():
        print("Copia de seguridad:", hacer_copia(app.config["SQLALCHEMY_DATABASE_URI"]).name)
        socios = importar_socios(libro)
        m_n, m_a = importar_movimientos(libro)
        c_n, c_a = importar_capital(libro)
        cierres = importar_cierres(libro)
        db.session.commit()
        print(f"✓ Socios: {socios} nuevos ({Socio.query.count()} en total)")
        print(f"  Movimientos: {m_n} nuevos, {m_a} actualizados")
        print(f"  Capital: {c_n} nuevos, {c_a} actualizados")
        print(f"  Cierres: {cierres} nuevos ({CierreMensual.query.count()} en total)")
        print(f"  Total en la base: {MovimientoContable.query.count()} movimientos, "
              f"{AporteCapital.query.count()} movimientos de capital")
