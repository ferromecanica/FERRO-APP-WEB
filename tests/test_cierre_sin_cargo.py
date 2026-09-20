"""Cerrar una OT sin cobrarla: auto propio, cortesía o garantía."""
from datetime import date
from wsgi import app
from app.extensions import db
from app.models import OrdenTrabajo, Venta
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))

with app.app_context():
    ot = OrdenTrabajo.query.filter(OrdenTrabajo.estado != 'Finalizada').first()
    otid, cliente = ot.id, ot.cliente
    assert cliente is not None, 'la prueba necesita una OT con cliente'
    ventas_antes = Venta.query.count()

# hay que decir qué pasó con el cobro
assert 'Indicá si el trabajo se cobró' in post(f'/ot/{otid}/cerrar', {'clasificacion': 'Otro'})

# cierre sin cargo
b = post(f'/ot/{otid}/cerrar', {'cobrado': 'sin_cargo', 'motivo_sin_cargo': 'Auto propio',
                                'clasificacion': 'Otro', 'fecha_fin': date.today().isoformat()})
assert 'cerrada sin cargo (Auto propio)' in b, b[:300]
assert 'Sin cargo' in b and 'Auto propio' in b

with app.app_context():
    ot = db.session.get(OrdenTrabajo, otid)
    assert ot.estado == 'Finalizada' and ot.sin_cargo and ot.motivo_sin_cargo == 'Auto propio'
    assert not ot.por_cobrar, 'no tiene que quedar por cobrar'
    assert ot.ventas == [], 'no tiene que generar venta'
    assert Venta.query.count() == ventas_antes, 'agregó una venta que no correspondía'
    costo = ot.costo_repuestos

# no aparece en el filtro "Por cobrar" ni en ventas
assert str(otid) not in B(c.get('/ot/?estado=por_cobrar'))
# en el listado se ve como cualquier OT terminada: el detalle es el que aclara
assert 'Sin cargo' not in B(c.get('/ot/'))
assert f'OT #{otid}' not in B(c.get('/ventas/'))

# y el costo de los repuestos sigue contando en la OT
if costo:
    assert f"{costo:,.0f}".replace(',', '.') in B(c.get(f'/ot/{otid}'))

# al reabrirla, deja de estar marcada
b = post(f'/ot/{otid}/reabrir')
with app.app_context():
    ot = db.session.get(OrdenTrabajo, otid)
    assert not ot.sin_cargo and ot.motivo_sin_cargo is None and ot.estado == 'En proceso'

# y se puede cerrar cobrando, como siempre
b = post(f'/ot/{otid}/cerrar', {'cobrado': 'si', 'total_cobrado': '120.000', 'metodo_pago': 'Efectivo',
                                'clasificacion': 'Otro', 'fecha_fin': date.today().isoformat()})
assert 'Venta registrada por $120.000' in b
with app.app_context():
    ot = db.session.get(OrdenTrabajo, otid)
    assert not ot.sin_cargo and ot.ventas and ot.ventas[0].total == 120000
print('TODO OK')
