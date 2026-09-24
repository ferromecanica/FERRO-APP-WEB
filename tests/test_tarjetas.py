"""Condiciones de pago: lo que descuenta la tarjeta y cuándo cae la plata.

Los números de referencia salen del reporte real de Getnet de junio a
septiembre de 2026 y del tarifario publicado en getnet.net/ar/aranceles.
"""
from datetime import date
from wsgi import app
from app.extensions import db
from app.models import Cliente, CondicionPago, MovimientoContable, OrdenTrabajo, Venta
from app.services import performance
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))

# ── Las condiciones vienen cargadas con las tarifas de Getnet ──
with app.app_context():
    nombres = [x.nombre for x in CondicionPago.query.order_by(CondicionPago.orden).all()]
    assert nombres == ['Efectivo', 'Transferencia', 'Débito', 'Crédito 1 pago',
                       'Crédito 3 cuotas', 'Crédito 6 cuotas', 'Mercado Pago'], nombres

    debito = CondicionPago.query.filter_by(nombre='Débito').one()
    assert round(debito.descuento, 2) == 1.21, debito.descuento      # 1 % + IVA
    assert round(debito.queda, 2) == 98.79

    un_pago = CondicionPago.query.filter_by(nombre='Crédito 1 pago').one()
    assert round(un_pago.descuento, 2) == 2.42                        # 2 % + IVA
    # Getnet liquidó la venta del 14/07/2026 el 24/07: 8 días hábiles
    assert un_pago.acredita(date(2026, 7, 14)) == date(2026, 7, 24)
    # y la del 27/07 el 06/08
    assert un_pago.acredita(date(2026, 7, 27)) == date(2026, 8, 6)

    # Débito: la venta del viernes 28/08 se liquidó el lunes 31/08
    assert debito.acredita(date(2026, 8, 28)) == date(2026, 8, 31)

    tres = CondicionPago.query.filter_by(nombre='Crédito 3 cuotas').one()
    assert tres.dias_habiles == 2 and tres.tasa_financiera == 7.41
    # Sobre los $159.500 reales, Getnet depositó $141.345,96
    assert abs(tres.neto(159500) - 141345.96) < 10, tres.neto(159500)

    seis = CondicionPago.query.filter_by(nombre='Crédito 6 cuotas').one()
    assert seis.tasa_financiera == 12.64                              # tarifario de Getnet
    assert round(seis.queda, 2) == 82.29

    # El recargo justo es lo que hay que cobrar para percibir lo calculado
    for cond in (debito, un_pago, tres, seis):
        assert abs(cond.neto(cond.bruto(100000)) - 100000) < 1, cond.nombre
    assert round(tres.recargo_justo, 2) == 12.85
    assert round(seis.recargo_justo, 2) == 21.53
    # Si se fija un recargo a mano, manda ese
    tres.recargo = 10.0
    assert tres.recargo_usado == 10.0
    tres.recargo = None
    assert round(tres.recargo_usado, 2) == 12.85

    # Efectivo no descuenta nada ni espera
    efectivo = CondicionPago.query.filter_by(nombre='Efectivo').one()
    assert efectivo.queda == 100 and efectivo.acredita(date(2026, 9, 18)) == date(2026, 9, 18)

    ot = OrdenTrabajo.query.filter_by(estado='En proceso').first()
    otid = ot.id
    cliente = Cliente.query.first(); cid = cliente.id
    id_tres, id_debito = tres.id, debito.id
    db.session.commit()

# ── Cerrar una OT con tarjeta: lo que se carga es lo que paga el cliente ──
post(f'/ot/{otid}/cerrar', {'cobrado': 'si', 'clasificacion': 'Otro', 'pago_total_1': '$ 180.000',
                            'pago_condicion_1': str(id_tres), 'fecha_fin': '2026-09-18', 'cliente_id': cid})
with app.app_context():
    v = Venta.query.filter_by(ot_id=otid).one()
    assert v.metodo_pago == 'Crédito 3 cuotas'
    assert v.bruto_cobrado == 180000, 'el cliente pagó lo que se cargó'
    assert abs(v.cobrado - 159505.02) < 1, v.cobrado                  # 180.000 − 11,39 %
    assert abs(v.costo_tarjeta - 20494.98) < 1, v.costo_tarjeta
    assert v.fecha_acreditacion == date(2026, 9, 22), v.fecha_acreditacion  # viernes + 2 hábiles
    # La comisión es un costo más: la ganancia sale de lo que percibimos
    assert abs(v.ganancia - (v.cobrado - v.costo_total)) < 0.01

    # El ingreso entra por lo que percibimos y el día que cae en el banco
    m = MovimientoContable.query.filter_by(venta_id=v.id).one()
    assert abs(m.total - 159505.02) < 1, m.total
    assert m.fecha == date(2026, 9, 22) and m.mes_imputacion == '2026-09'
    assert 'se cobraron' in m.concepto, m.concepto
    vid = v.id

# ── La plata que todavía no entró se ve ──
with app.app_context():
    camino = performance.en_camino(date(2026, 9, 19))
    assert [x.id for x in camino['ventas']] == [vid]
    assert abs(camino['total'] - 159505.02) < 1
    # Después de la fecha ya no está en camino
    assert performance.en_camino(date(2026, 9, 30))['ventas'] == []

b = B(c.get(f'/ventas/{vid}'))
assert 'Percibimos' in b and 'Pagó el cliente' in b

# ── Mostrador con débito ──
post('/ventas/mostrador/items', {'tipo': 'manual', 'descripcion': 'Cambio de lamparita',
                                 'precio': '50.000', 'costo': '0'})
post('/ventas/mostrador/cobrar', {'pago_condicion_1': str(id_debito), 'fecha': '2026-09-18'})
with app.app_context():
    v = Venta.query.filter_by(ot_id=None).order_by(Venta.id.desc()).first()
    assert v.metodo_pago == 'Débito'
    assert v.bruto_cobrado == 50000, v.bruto_cobrado
    assert abs(v.cobrado - 49395) < 1, v.cobrado                      # 50.000 − 1,21 %
    assert v.fecha_acreditacion == date(2026, 9, 21), v.fecha_acreditacion  # viernes + 1 hábil

# ── Sin forma de pago no se cobra ──
post('/ventas/mostrador/items', {'tipo': 'manual', 'descripcion': 'Otra cosa', 'precio': '1.000'})
assert 'Elegí la forma de pago' in post('/ventas/mostrador/cobrar', {'fecha': '2026-09-18'})

# ── Pago partido: una parte en efectivo y el resto con tarjeta ──
with app.app_context():
    id_efectivo = CondicionPago.query.filter_by(nombre='Efectivo').one().id
    assert db.session.get(CondicionPago, id_efectivo).destino == 'Caja', 'el efectivo va a la caja de Iván'
    id_seis = CondicionPago.query.filter_by(nombre='Crédito 6 cuotas').one().id
    assert db.session.get(CondicionPago, id_seis).destino == 'Banco'

post('/ventas/mostrador/items', {'tipo': 'manual', 'descripcion': 'Trabajo partido',
                                 'precio': '100.000', 'costo': '0'})
post('/ventas/mostrador/cobrar', {'pago_condicion_1': str(id_efectivo), 'pago_total_1': '60.000',
                                  'pago_condicion_2': str(id_seis), 'pago_total_2': '40.000',
                                  'fecha': '2026-09-18'})
with app.app_context():
    v = Venta.query.filter_by(ot_id=None).order_by(Venta.id.desc()).first()
    assert len(v.pagos) == 2, v.pagos
    efectivo, tarjeta = v.pagos
    assert efectivo.bruto == 60000 and efectivo.neto == 60000, 'el efectivo no paga comisión'
    assert efectivo.fecha_acreditacion == date(2026, 9, 18), 'el efectivo está el mismo día'
    assert efectivo.condicion.destino == 'Caja'
    assert tarjeta.bruto == 40000 and tarjeta.neto < 40000, 'la tarjeta se queda con lo suyo'
    assert tarjeta.fecha_acreditacion > efectivo.fecha_acreditacion, 'la tarjeta cae después'
    # El resumen de la venta suma las partes, para las pantallas que lo leen
    assert v.bruto_cobrado == 100000 and abs(v.cobrado - (60000 + tarjeta.neto)) < 1
    assert v.metodo_pago == 'Efectivo + Crédito 6 cuotas', v.metodo_pago
    assert v.fecha_acreditacion == tarjeta.fecha_acreditacion, 'termina de cobrarse con la última parte'

    # Cada parte deja su propio ingreso, con su fecha: el efectivo ya está y la tarjeta no
    movs = MovimientoContable.query.filter_by(venta_id=v.id).order_by(MovimientoContable.fecha).all()
    assert len(movs) == 2, movs
    assert movs[0].total == 60000 and movs[0].fecha == date(2026, 9, 18)
    assert abs(movs[1].total - tarjeta.neto) < 1 and movs[1].fecha == tarjeta.fecha_acreditacion
    assert sum(m.total for m in movs) == v.cobrado

# Anularla se lleva los dos ingresos
post(f'/ventas/{v.id}/anular')
with app.app_context():
    assert not MovimientoContable.query.filter_by(venta_id=v.id).count(), 'quedaron ingresos sin venta'

# ── Se editan desde Configuración ──
b = B(c.get('/configuracion'))
assert 'Comisiones de tarjeta' in b and 'Crédito 6 cuotas' in b
post('/configuracion/condiciones', {f'nombre_{id_debito}': 'Débito', f'dias_{id_debito}': '2',
                                    f'arancel_{id_debito}': '1,53', f'tasa_{id_debito}': '',
                                    f'recargo_{id_debito}': '', f'activa_{id_debito}': '1'})
with app.app_context():
    d = db.session.get(CondicionPago, id_debito)
    assert d.arancel == 1.53 and d.dias_habiles == 2, (d.arancel, d.dias_habiles)
    assert round(d.descuento, 4) == round(1.53 * 1.21, 4)

print('TARJETAS OK')
