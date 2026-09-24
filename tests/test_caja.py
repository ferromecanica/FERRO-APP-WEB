"""La caja chica de Iván: lo que entra en efectivo, lo que sale y el saldo."""
from datetime import date, timedelta
from wsgi import app
from app.extensions import db
from app.models import CondicionPago, MovimientoCaja, MovimientoContable
from app.services import caja
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))

HOY = date.today()

with app.app_context():
    id_efectivo = CondicionPago.query.filter_by(nombre='Efectivo').one().id
    id_debito = CondicionPago.query.filter_by(nombre='Débito').one().id
    assert caja.saldo() == 0, 'la caja arranca en cero'

# ── La apertura: lo que ya había el día que se empezó a llevar ──
post('/administracion/caja/nuevo', {'tipo': 'Apertura', 'monto': '50.000', 'concepto': 'Lo que había'})
with app.app_context():
    assert caja.saldo() == 50000, caja.saldo()
    assert caja.resumen()['hay_apertura']

# ── El efectivo de una venta entra solo; lo que va al banco no ──
post('/ventas/mostrador/items', {'tipo': 'manual', 'descripcion': 'Service', 'precio': '100.000', 'costo': '0'})
post('/ventas/mostrador/cobrar', {'pago_condicion_1': str(id_efectivo), 'pago_total_1': '70.000',
                                  'pago_condicion_2': str(id_debito), 'pago_total_2': '30.000',
                                  'fecha': HOY.isoformat()})
with app.app_context():
    assert caja.entradas_por_ventas() == 70000, 'a la caja va solo la parte en efectivo'
    assert caja.saldo() == 120000, caja.saldo()

# ── Un gasto sale de la caja y además es egreso del mes ──
post('/administracion/caja/nuevo', {'tipo': 'Gasto', 'monto': '12.000',
                                    'concepto': 'Tornillería', 'quien': 'Ferretería López'})
with app.app_context():
    assert caja.saldo() == 108000, caja.saldo()
    m = MovimientoCaja.query.filter_by(tipo='Gasto').one()
    assert m.movimiento is not None, 'el gasto tiene que dejar su egreso'
    assert m.movimiento.tipo == 'Egreso' and m.movimiento.total == 12000
    assert 'caja chica' in m.movimiento.concepto
    gid = m.id

# ── Lo que pasa al banco o se lleva un socio NO es gasto del mes ──
post('/administracion/caja/nuevo', {'tipo': 'Pasa al banco', 'monto': '40.000', 'concepto': 'Depósito'})
post('/administracion/caja/nuevo', {'tipo': 'Retiro de socio', 'monto': '8.000', 'quien': 'Lucio'})
with app.app_context():
    assert caja.saldo() == 60000, caja.saldo()
    for tipo in ('Pasa al banco', 'Retiro de socio'):
        assert MovimientoCaja.query.filter_by(tipo=tipo).one().movimiento is None, \
            f'«{tipo}» no es un gasto: la plata cambia de lugar'
    r = caja.resumen()
    assert r['al_banco'] == 40000 and r['retiros'] == 8000 and r['gastos'] == 12000

# ── El extracto: del más nuevo al más viejo, con el saldo de cada punto ──
with app.app_context():
    filas = caja.movimientos()
    assert len(filas) == 5, filas                      # apertura + venta + gasto + banco + retiro
    assert filas[0]['saldo'] == 60000, 'la primera fila es la última que pasó'
    assert filas[-1]['tipo'] in ('Apertura', 'Venta'), 'la última es la más vieja'
    venta = next(f for f in filas if f['venta_id'])
    assert venta['monto'] == 70000 and venta['movimiento'] is None, 'la venta no se borra desde la caja'

b = B(c.get('/administracion/caja'))
assert 'Caja chica' in b and '$ 60.000' in b
assert 'Tornillería' in b and 'Depósito' in b

# ── Borrar un gasto se lleva también su egreso ──
with app.app_context():
    mid = db.session.get(MovimientoCaja, gid).movimiento_id
post(f'/administracion/caja/{gid}/eliminar')
with app.app_context():
    assert db.session.get(MovimientoCaja, gid) is None
    assert db.session.get(MovimientoContable, mid) is None, 'quedó el egreso de un gasto borrado'
    assert caja.saldo() == 72000, caja.saldo()

# ── El saldo a una fecha: lo de mañana todavía no cuenta ──
post('/administracion/caja/nuevo', {'tipo': 'Gasto', 'monto': '5.000', 'concepto': 'De mañana',
                                    'fecha': (HOY + timedelta(days=1)).isoformat()})
with app.app_context():
    assert caja.saldo(HOY) == 72000, 'un gasto de mañana no puede bajar el saldo de hoy'
    assert caja.saldo(HOY + timedelta(days=1)) == 67000

# ── Anular la venta se lleva su efectivo de la caja ──
with app.app_context():
    from app.models import Venta
    vid = Venta.query.order_by(Venta.id.desc()).first().id
post(f'/ventas/{vid}/anular')
with app.app_context():
    assert caja.entradas_por_ventas() == 0, 'la venta anulada no puede seguir en la caja'
    assert caja.saldo(HOY) == 2000, caja.saldo(HOY)   # 50.000 − 40.000 − 8.000

print('CAJA OK')
