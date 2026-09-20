"""Administración: movimientos, capital y el cierre del mes."""
import re
from datetime import date
from wsgi import app
from app.extensions import db
from app.models import AporteCapital, CierreMensual, MovimientoContable, Socio
from app.services import cierre as calculo
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))

MES = '2026-08'
with app.app_context():
    MovimientoContable.query.delete()
    AporteCapital.query.delete()
    CierreMensual.query.delete()
    Socio.query.delete()
    ivan = Socio(nombre='Iván', sueldo_base=2449987, participacion=.5, orden=1)
    lucio = Socio(nombre='Lucio', sueldo_base=435000, participacion=.5, orden=2)
    db.session.add_all([ivan, lucio])
    db.session.flush()
    # Lucio puso el 88 % del capital
    db.session.add_all([AporteCapital(fecha=date(2026, 1, 23), socio=lucio, pesos=3375556, cotizacion=1429),
                        AporteCapital(fecha=date(2026, 3, 5), socio=ivan, pesos=450000, cotizacion=1415)])
    db.session.commit()
    ivan_id, lucio_id = ivan.id, lucio.id

# ── movimientos ──
b = post('/administracion/nuevo', {'tipo': 'Ingreso', 'fecha': '2026-08-15', 'mes_imputacion': MES,
                                   'quien': 'Cotraser S.A', 'concepto': 'Trabajos', 'total': '7.141.326',
                                   'clasificacion': 'Ventas', 'comprobante': 'Factura A', 'cobrado': '1'})
assert 'Movimiento registrado' in b
post('/administracion/nuevo', {'tipo': 'Ingreso', 'fecha': '2026-08-20', 'mes_imputacion': MES,
                               'quien': 'GTI', 'concepto': 'Sin cobrar', 'total': '350.000'})
post('/administracion/nuevo', {'tipo': 'Egreso', 'fecha': '2026-08-10', 'mes_imputacion': MES,
                               'quien': 'Filtros San Pablo', 'concepto': 'Aceite', 'total': '407.795,20',
                               'clasificacion': 'Repuestos y Proveedores'})
post('/administracion/nuevo', {'tipo': 'Colchón', 'fecha': '2026-08-01', 'mes_imputacion': MES,
                               'concepto': 'Colchón de julio', 'total': '900.000'})
# un egreso que NO cuenta: liquidación de sueldo
post('/administracion/nuevo', {'tipo': 'Egreso', 'fecha': '2026-08-31', 'mes_imputacion': MES,
                               'quien': 'Iván', 'concepto': 'Sueldo', 'total': '1.000.000',
                               'clasificacion': 'Sueldos', 'comprobante': 'Liquidación'})
# el importe se arma solo con neto + iva si no se pone total
post('/administracion/nuevo', {'tipo': 'Egreso', 'fecha': '2026-08-05', 'mes_imputacion': MES,
                               'quien': 'Proveedor', 'concepto': 'Con IVA', 'neto': '100.000', 'iva': '21.000',
                               'total': '', 'clasificacion': 'Gasto Operativo'})
with app.app_context():
    con_iva = MovimientoContable.query.filter_by(concepto='Con IVA').one()
    assert con_iva.total == 121000, con_iva.total

# se puede escribir una clasificación que no está en la lista
post('/administracion/nuevo', {'tipo': 'Egreso', 'fecha': '2026-08-12', 'mes_imputacion': MES,
                               'quien': 'Municipalidad', 'concepto': 'Habilitación', 'total': '80.000',
                               'clasificacion': 'Impuestos y tasas'})
with app.app_context():
    assert MovimientoContable.query.filter_by(clasificacion='Impuestos y tasas').count() == 1
assert 'Impuestos y tasas' in B(c.get('/administracion/nuevo')), 'la nueva clasificación tiene que quedar en la lista'
with app.app_context():
    MovimientoContable.query.filter_by(clasificacion='Impuestos y tasas').delete()
    db.session.commit()

# ── la cuenta del mes ──
with app.app_context():
    n = calculo.numeros_del_mes(MES)
    assert n['ingresos'] == 7141326 and n['sin_cobrar'] == 350000
    assert n['egresos'] == 407795.20 + 121000, n['egresos']   # sin la liquidación
    assert n['colchon_entrante'] == 900000

    p = calculo.calcular(MES)
    assert p['resultado'] == round(7141326 - 528795.20 + 900000, 2)
    # los dos cobran el mismo porcentaje de su sueldo base
    sueldos = {f['socio'].nombre: f['sueldo'] for f in p['reparto']}
    assert sueldos['Iván'] == 2449987 and sueldos['Lucio'] == 435000  # alcanza para los dos enteros

    # apartando un colchón, los sueldos bajan a prorrata (como los cierres reales)
    con_colchon = calculo.calcular(MES, colchon_objetivo=5000000)
    s = {f['socio'].nombre: f['sueldo'] for f in con_colchon['reparto']}
    proporcion = (con_colchon['disponible'] - 5000000) / (2449987 + 435000)
    assert abs(s['Iván'] - 2449987 * proporcion) < 1 and abs(s['Lucio'] - 435000 * proporcion) < 1
    assert abs(s['Iván'] / s['Lucio'] - 2449987 / 435000) < 0.01, 'la proporción entre socios se mantiene'
    assert con_colchon['colchon'] >= 5000000
    # con deuda de capital: 40 % repago, 30 % ganancia, 30 % colchón
    assert abs(p['repago'] - p['remanente'] * .40) < 1
    assert abs(p['ganancia'] - p['remanente'] * .30) < 1
    assert abs(p['colchon'] - p['remanente'] * .30) < 1
    # el repago va proporcional a lo aportado, la ganancia mitad y mitad
    repagos = {f['socio'].nombre: f['repago'] for f in p['reparto']}
    assert repagos['Lucio'] > repagos['Iván'] * 6, repagos
    ganancias = {f['socio'].nombre: f['ganancia'] for f in p['reparto']}
    assert abs(ganancias['Lucio'] - ganancias['Iván']) < 1

# ── cerrar el mes ──
b = post(f'/administracion/cierres/{MES}', {'accion': 'cerrar', 'modo': 'Automático',
                                            'fecha_cierre': '2026-08-31', 'cotizacion': '1.535'})
assert 'cerrado' in b.lower()
with app.app_context():
    cierre = CierreMensual.query.filter_by(mes=MES).one()
    assert cierre.cerrado and cierre.colchon > 0
    # quedaron las liquidaciones de sueldo y el colchón del mes que viene
    generados = MovimientoContable.query.filter_by(cierre_id=cierre.id).all()
    assert any(m.comprobante == 'Liquidación' and m.quien == 'Iván' for m in generados)
    colchon = [m for m in generados if m.tipo == 'Colchón']
    assert len(colchon) == 1 and colchon[0].mes_imputacion == '2026-09'
    assert abs(colchon[0].total - cierre.colchon) < 0.01
    # y la devolución de capital
    devoluciones = AporteCapital.query.filter_by(cierre_id=cierre.id).all()
    assert devoluciones and all(d.devuelve for d in devoluciones)
    capital_despues = Socio.query.filter_by(id=lucio_id).one().capital_pesos

# los generados no se editan a mano
with app.app_context():
    uno = MovimientoContable.query.filter_by(cierre_id=cierre.id).first()
    assert uno.automatico
    uno_id = uno.id
assert 'no se borra desde acá' in post(f'/administracion/{uno_id}/eliminar')

# ── reabrir: se borra lo generado ──
b = post(f'/administracion/cierres/{MES}', {'accion': 'reabrir'})
assert 'abierto de nuevo' in b
with app.app_context():
    assert CierreMensual.query.filter_by(mes=MES).first() is None
    assert MovimientoContable.query.filter_by(tipo='Colchón', mes_imputacion='2026-09').count() == 0
    assert AporteCapital.query.filter(AporteCapital.tipo == 'Devolución de Capital').count() == 0

# ── sin deuda de capital, el reparto es 0 / 50 / 50 ──
with app.app_context():
    AporteCapital.query.delete()
    db.session.commit()
    p = calculo.calcular(MES)
    assert p['repago'] == 0
    assert abs(p['ganancia'] - p['remanente'] * .50) < 1
    assert abs(p['colchon'] - p['remanente'] * .50) < 1
# ── la circular para el equipo ──
from app.services import drive, reporte
enviados = []
def falso(accion, **datos):
    enviados.append(dict(datos, accion=accion))
    return {"ok": True, "url": "https://drive.google.com/file/d/xyz/view"}
drive.llamar, original = falso, drive.llamar
reporte.configurado, original_cfg = (lambda: True), reporte.configurado

# con el mes abierto sale el preliminar, con sus compromisos y observaciones
post(f'/administracion/cierres/{MES}', {'accion': 'guardar', 'colchon_objetivo': '900.000',
                                        'compromiso_concepto': 'Alquiler', 'compromiso_total': '988.735',
                                        'compromiso_dejar': '800.000', 'caja_chica': '947.800',
                                        'banco': '1.992.931', 'observaciones': 'Compramos herramientas.'})
b = post(f'/administracion/cierres/{MES}/circular')
assert 'Circular generada' in b and 'PRELIMINAR' in b
html = enviados[-1]['html']
assert 'CIRCULAR CONTABLE' in html.upper()
assert 'Alquiler' in html and '988.735' in html
assert 'Compramos herramientas' in html
assert '947.800' in html and '1.992.931' in html
assert 'PRELIMINAR' in html, 'con el mes abierto tiene que avisar que es preliminar'
with app.app_context():
    cc = CierreMensual.query.filter_by(mes=MES).one()
    assert cc.link_circular and cc.numero and cc.compromisos
    assert cc.compromisos[0].concepto == 'Alquiler'

# ya cerrado, la circular sale definitiva
post(f'/administracion/cierres/{MES}', {'accion': 'cerrar', 'modo': 'Automático', 'colchon_objetivo': '900.000',
                                        'fecha_cierre': '2026-08-31', 'cotizacion': '1.535',
                                        'compromiso_concepto': 'Alquiler', 'compromiso_total': '988.735',
                                        'compromiso_dejar': '800.000'})
b = post(f'/administracion/cierres/{MES}/circular')
assert 'Circular generada' in b and 'PRELIMINAR' not in b
assert 'PRELIMINAR' not in enviados[-1]['html']

drive.llamar, reporte.configurado = original, original_cfg

print('TODO OK')
