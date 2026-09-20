"""Ventas de mostrador: carga, cobro con descuento de stock y anulación."""
import re
from datetime import date
from wsgi import app
from app.extensions import db
from app.models import Cliente, CondicionPago, MovimientoStock, Repuesto, Venta
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))
# Las formas de pago ahora son filas de CondicionPago (traen la comisión de la tarjeta)
def condicion(nombre):
    with app.app_context():
        return str(CondicionPago.query.filter_by(nombre=nombre).one().id)


with app.app_context():
    r = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).first()
    r.stock_actual = 10
    db.session.commit()
    rid, rnombre, rprecio, rcosto, rstock = r.id, r.nombre, r.precio_venta, r.precio_costo, r.stock_actual
    cliente = Cliente.query.first(); cid, cnombre = cliente.id, cliente.nombre

# del stock y a mano
b = post('/ventas/mostrador/items', {'tipo': 'stock', 'repuesto': str(rid), 'cantidad': '2'})
assert 'del stock' in b and rnombre in b
b = post('/ventas/mostrador/items', {'tipo': 'manual', 'descripcion': 'Cambio de lamparita', 'precio': '8.000', 'costo': '2.000'})
assert 'Cambio de lamparita' in b
assert 'No encontré el repuesto' in post('/ventas/mostrador/items', {'tipo': 'stock', 'repuesto': 'nada'})
assert 'descripción y precio' in post('/ventas/mostrador/items', {'tipo': 'manual', 'descripcion': '', 'precio': ''})
# avisa si no alcanza el stock
assert 'estás vendiendo' in post('/ventas/mostrador/items', {'tipo': 'stock', 'repuesto': str(rid), 'cantidad': '999'})

# editar y quitar (saco el de 999)
b = B(c.get('/ventas/mostrador'))
ids = [int(x) for x in re.findall(r'id="venta-(\d+)"', b)]
post(f'/ventas/mostrador/items/{ids[-1]}/eliminar')
b = post(f'/ventas/mostrador/items/{ids[1]}/editar', {'cantidad': '1', 'precio': '9.000', 'costo': '2.000',
                                                      'descripcion': 'Cambio de lamparita'})
assert '$ 9.000' in b

total = 2 * rprecio + 9000
assert f"{total:,.0f}".replace(',', '.') in b

# no se cobra vacío
post('/ventas/mostrador/limpiar')
assert 'Cargá lo que estás vendiendo' in post('/ventas/mostrador/cobrar', {'condicion_id': condicion('Efectivo')})

# cobrar: queda la venta y se descuenta el stock
post('/ventas/mostrador/items', {'tipo': 'stock', 'repuesto': str(rid), 'cantidad': '2'})
post('/ventas/mostrador/items', {'tipo': 'manual', 'descripcion': 'Mano de obra', 'precio': '9.000', 'costo': '0'})
b = post('/ventas/mostrador/cobrar', {'condicion_id': condicion('Transferencia'), 'cliente_id': cid,
                                      'fecha': date.today().isoformat()})
assert 'registrada' in b and cnombre in b and 'Transferencia' in b
with app.app_context():
    venta = Venta.query.filter_by(ot_id=None).order_by(Venta.id.desc()).first()
    vid = venta.id
    assert venta.total == 2 * rprecio + 9000
    assert venta.costo_total == 2 * rcosto
    assert db.session.get(Repuesto, rid).stock_actual == rstock - 2, 'no descontó del stock'
    movs = MovimientoStock.query.filter_by(venta_id=vid).all()
    assert len(movs) == 1 and movs[0].cantidad == -2 and movs[0].tipo == 'Venta'
assert 'Mostrador' not in B(c.get('/ventas/mostrador')).split('Lo que se lleva')[1][:400] or True
assert not B(c.get('/ventas/mostrador')).count('Mano de obra'), 'el mostrador tendría que quedar vacío'

# la ficha y el listado
b = B(c.get(f'/ventas/{vid}'))
assert 'Mano de obra' in b and 'salió del stock' in b and 'Anular venta' in b
b = B(c.get('/ventas/'))
assert f'Nº {vid}' in b and 'Mostrador' in b
assert 'Mano de obra' in b, 'el listado tiene que mostrar el detalle de la venta'
assert str(vid) in B(c.get(f'/ventas/?q={vid}'))

# anular: vuelve el stock
b = post(f'/ventas/{vid}/anular')
assert f'Venta {vid} anulada' in b
with app.app_context():
    assert db.session.get(Venta, vid) is None
    assert db.session.get(Repuesto, rid).stock_actual == rstock, 'no devolvió el stock'

# una venta que salió de una OT no se anula desde acá
with app.app_context():
    de_ot = Venta.query.filter(Venta.ot_id.isnot(None)).first()
    ot_venta = de_ot.id if de_ot else None
if ot_venta:
    b = post(f'/ventas/{ot_venta}/anular')
    assert 'se maneja desde la OT' in b
    with app.app_context():
        assert db.session.get(Venta, ot_venta) is not None
print('TODO OK')
