"""Performance: que los números den lo mismo que el cierre y que los relojes pinten."""
from datetime import date
from wsgi import app
from app.extensions import db
from app.models import Cliente, MovimientoContable, Venta, VentaItem
from app.services import performance
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)

HOY = date(2026, 9, 20)
MES = '2026-09'

with app.app_context():
    cliente = Cliente.query.first(); cid = cliente.id
    # Un mes armado a mano: entran 2.000.000, salen 800.000 y viene un colchón de 500.000
    db.session.add_all([
        MovimientoContable(fecha=HOY, tipo='Ingreso', mes_imputacion=MES, total=2000000,
                           cobrado=True, quien='Cliente', concepto='Trabajos'),
        MovimientoContable(fecha=HOY, tipo='Egreso', mes_imputacion=MES, total=800000,
                           clasificacion='Repuestos y Proveedores', quien='Proveedor', concepto='Repuestos'),
        MovimientoContable(fecha=HOY, tipo='Colchón', mes_imputacion=MES, total=500000,
                           concepto='Colchón de agosto'),
        # Ni los sueldos ni el capital entran en el resultado operativo
        MovimientoContable(fecha=HOY, tipo='Egreso', mes_imputacion=MES, total=1500000,
                           comprobante='Liquidación', concepto='Sueldos'),
        MovimientoContable(fecha=HOY, tipo='Egreso', mes_imputacion=MES, total=300000,
                           clasificacion='Inversión de Capital', concepto='Devolución de capital'),
    ])
    db.session.commit()

    plata = performance.resultado_del_mes(MES)
    assert plata['ingresos'] == 2000000, plata
    assert plata['egresos'] == 800000, 'los sueldos y el capital no son gasto operativo'
    assert plata['colchon'] == 500000, plata
    # El mismo criterio que el cierre mensual: ingresos − egresos + colchón
    assert plata['resultado'] == 1700000, plata['resultado']

# ── Los colores del reloj de facturación ──
assert performance.tono(-10) == ''
assert performance.tono(5) == ''
assert performance.tono(-25) == 'tono-aviso'
assert performance.tono(-39) == 'tono-aviso'
assert performance.tono(-40) == 'tono-malo'
assert performance.tono(-80) == 'tono-malo'

# ── La comparación es contra el mismo tramo de días, no contra meses enteros ──
with app.app_context():
    antes = {f['clave']: f['total'] for f in performance.facturacion_al_dia(HOY)}
    for fecha, monto in [(date(2026, 8, 5), 100000), (date(2026, 8, 28), 900000),
                         (date(2026, 9, 5), 300000)]:
        v = Venta(fecha=fecha, cliente_id=cid, metodo_pago='Efectivo')
        v.items.append(VentaItem(descripcion='Trabajo', cantidad=1, precio_unitario=monto, costo_unitario=0))
        db.session.add(v)
    db.session.commit()

    filas = {f['clave']: f for f in performance.facturacion_al_dia(HOY)}
    assert filas['2026-08']['total'] - antes['2026-08'] == 100000, \
        'al día 20 no tiene que contar la venta del 28 de agosto'
    assert filas['2026-09']['total'] - antes['2026-09'] == 300000, filas['2026-09']
    assert filas['2026-09']['actual'] and not filas['2026-08']['actual']

# ── La pantalla abre y muestra los pedazos de las tortas ──
b = B(c.get('/administracion/performance'))
assert 'Performance' in b and 'Mes a mes' in b
assert 'stroke-dasharray' in b, 'no dibujó los relojes ni las tortas'
assert 'Repuestos y Proveedores' in b

print('PERFORMANCE OK')
