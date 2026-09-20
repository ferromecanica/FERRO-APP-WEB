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

    # El recargo justo deja exactamente lo facturado en el banco
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

# ── Cerrar una OT con tarjeta: la venta guarda las tres cosas ──
post(f'/ot/{otid}/cerrar', {'cobrado': 'si', 'clasificacion': 'Otro', 'total_cobrado': '$ 98.000',
                            'condicion_id': str(id_tres), 'fecha_fin': '2026-09-18', 'cliente_id': cid})
with app.app_context():
    v = Venta.query.filter_by(ot_id=otid).one()
    assert v.metodo_pago == 'Crédito 3 cuotas'
    assert v.total == 98000, 'lo facturado no cambia'
    assert abs(v.bruto_cobrado - 110592.13) < 1, v.bruto_cobrado      # 98.000 + 12,85 %
    assert abs(v.neto_acreditado - 98000) < 1, v.neto_acreditado
    assert v.fecha_acreditacion == date(2026, 9, 22), v.fecha_acreditacion  # viernes + 2 hábiles
    assert abs(v.costo_tarjeta - 12592.13) < 1, v.costo_tarjeta

    # El ingreso entra por el neto y el día que cae en el banco
    m = MovimientoContable.query.filter_by(venta_id=v.id).one()
    assert abs(m.total - 98000) < 1, m.total
    assert m.fecha == date(2026, 9, 22) and m.mes_imputacion == '2026-09'
    assert 'se cobraron' in m.concepto, m.concepto
    vid = v.id

# ── La plata que todavía no entró se ve ──
with app.app_context():
    camino = performance.en_camino(date(2026, 9, 19))
    assert [x.id for x in camino['ventas']] == [vid]
    assert abs(camino['total'] - 98000) < 1
    # Después de la fecha ya no está en camino
    assert performance.en_camino(date(2026, 9, 30))['ventas'] == []

b = B(c.get(f'/ventas/{vid}'))
assert 'Entra al banco' in b and 'Se le cobró' in b

# ── Mostrador con débito ──
post('/ventas/mostrador/items', {'tipo': 'manual', 'descripcion': 'Cambio de lamparita',
                                 'precio': '50.000', 'costo': '0'})
post('/ventas/mostrador/cobrar', {'condicion_id': str(id_debito), 'fecha': '2026-09-18'})
with app.app_context():
    v = Venta.query.filter_by(ot_id=None).order_by(Venta.id.desc()).first()
    assert v.metodo_pago == 'Débito'
    assert abs(v.bruto_cobrado - 50612.34) < 1, v.bruto_cobrado       # 50.000 + 1,22 %
    assert abs(v.neto_acreditado - 50000) < 1
    assert v.fecha_acreditacion == date(2026, 9, 21), v.fecha_acreditacion  # viernes + 1 hábil

# ── Sin forma de pago no se cobra ──
post('/ventas/mostrador/items', {'tipo': 'manual', 'descripcion': 'Otra cosa', 'precio': '1.000'})
assert 'Elegí la forma de pago' in post('/ventas/mostrador/cobrar', {'fecha': '2026-09-18'})

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
