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

# ── Los colores del reloj: amarillo a partir del 20 % abajo, rojo del 30 % ──
assert performance.tono(-10) == ''
assert performance.tono(5) == ''
assert performance.tono(-19) == ''
assert performance.tono(-20) == 'tono-aviso'
assert performance.tono(-29) == 'tono-aviso'
assert performance.tono(-30) == 'tono-malo'
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

# ── El resultado se compara contra los meses anteriores, no contra la nada ──
with app.app_context():
    from app.services.performance import _mes_de, _restar_meses
    for n, monto in ((2, 900000), (1, 700000)):
        mes = _restar_meses(HOY, n)
        db.session.add(MovimientoContable(fecha=mes, tipo='Ingreso', mes_imputacion=_mes_de(mes),
                                          total=monto, concepto='De un mes anterior', cobrado=True))
    db.session.commit()
    t = performance.relojes_del_mes(HOY)
    assert t['promedio_resultado'] == 800000, t['promedio_resultado']
    assert t['relojes']['resultado'].get('marca'), 'el reloj del resultado tiene que marcar el promedio'
    assert 'tx' in t['relojes']['resultado']['marca'], 'falta dónde escribir el importe del promedio'

# Los dos relojes que comparan muestran el promedio escrito en el dibujo
b = B(c.get('/administracion/performance'))
assert 'Promedio últimos 6 meses' in b and 'la rayita' not in b
assert 'marca-texto' in b, 'no escribió el promedio sobre su marca'
# Y el Tablero dibuja los mismos cuatro relojes, sin la tarjeta de Reponer
b = B(c.get('/'))
assert 'Cómo viene el mes' in b and 'marca-texto' in b
assert 'Reponer' not in b

# ── El resultado se mide al día, no contra meses enteros ──
# Si no, el día 5 se compara una semana contra meses completos y siempre da rojo.
with app.app_context():
    from app.services.performance import _mes_de, _restar_meses, resultado_del_mes
    # Se limpian esos meses para que la cuenta sea exacta: antes se cargaron otros
    meses_prueba = [_mes_de(_restar_meses(HOY, n)) for n in (1, 2, 3)]
    MovimientoContable.query.filter(MovimientoContable.mes_imputacion.in_(meses_prueba)).delete(
        synchronize_session=False)
    # En cada uno de los 3 meses anteriores: 100.000 el día 5 y 900.000 el día 25
    for n in (1, 2, 3):
        mes = _restar_meses(HOY, n)
        for dia, monto in ((5, 100000), (25, 900000)):
            f = mes.replace(day=dia)
            db.session.add(MovimientoContable(fecha=f, tipo='Ingreso', mes_imputacion=_mes_de(f),
                                              total=monto, concepto=f'Prueba al día {dia}', cobrado=True))
    db.session.commit()

    # Al día 10 solo cuentan los del día 5 de cada mes
    for n in (1, 2, 3):
        mes = _mes_de(_restar_meses(HOY, n))
        assert resultado_del_mes(mes, 10)['resultado'] == 100000, mes
        assert resultado_del_mes(mes, 25)['resultado'] == 1000000, mes
        assert resultado_del_mes(mes)['resultado'] == 1000000, 'sin día, el mes entero'

    dia10 = date(HOY.year, HOY.month, 10)
    assert performance.promedio_de_resultados(dia10) == 100000, 'el promedio tiene que ser al día 10'
    assert performance.promedio_de_resultados(dia10, al_dia=False) == 1000000, 'y el de meses enteros, entero'

    # El 31 no existe en todos los meses: no se puede pasar del último día
    corto = _mes_de(date(2026, 2, 1))
    assert resultado_del_mes(corto, 31)['resultado'] == resultado_del_mes(corto)['resultado']

# Y el reloj compara lo que va del mes contra ese promedio al mismo día
with app.app_context():
    t = performance.relojes_del_mes(dia10)
    assert t['plata']['resultado'] == resultado_del_mes(_mes_de(dia10), 10)['resultado']
    assert t['promedio_resultado'] == 100000
b = B(c.get('/administracion/performance'))
assert 'al día' in b, 'la tarjeta no aclara que la comparación es al mismo día del mes'

# Con un promedio negativo no se compara: el porcentaje no significaría nada
with app.app_context():
    MovimientoContable.query.filter(MovimientoContable.mes_imputacion.in_(meses_prueba)).delete(
        synchronize_session=False)
    for n in (1, 2, 3):
        mes = _restar_meses(HOY, n).replace(day=5)
        db.session.add(MovimientoContable(fecha=mes, tipo='Egreso', mes_imputacion=_mes_de(mes),
                                          total=50000, concepto='Mes malo', cobrado=True))
    db.session.commit()
    t = performance.relojes_del_mes(dia10)
    assert t['promedio_resultado'] == 0 and t['contra_resultado'] == 0, t['contra_resultado']
    assert t['tono_resultado'] == '', 'no puede pintarse rojo o verde sin con qué comparar'

print('PERFORMANCE OK')
