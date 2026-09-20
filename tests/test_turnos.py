"""Turnos: agenda, alta con o sin cliente, estados y el paso a OT."""
import re
from datetime import date, timedelta
from wsgi import app
from app.extensions import db
from app.models import Cliente, OrdenTrabajo, Turno, Vehiculo
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))

hoy = date.today()
with app.app_context():
    cliente = Cliente.query.filter(Cliente.vehiculos.any()).first()
    cid, vid, nombre = cliente.id, cliente.vehiculos[0].id, cliente.nombre
    patente = cliente.vehiculos[0].patente

# turno de un cliente con auto
b = post('/turnos/nuevo', {'fecha': hoy.isoformat(), 'hora': '09:30', 'cliente_id': cid, 'vehiculo_id': vid,
                           'motivo': 'Service 10.000 km', 'duracion_valor': '2', 'duracion_unidad': 'Horas',
                           'estado': 'Confirmado', 'observaciones': 'Lo trae el hijo'})
assert 'agendado' in b and nombre in b and patente in b, b[:400]
assert 'Service 10.000 km' in b and '2 horas' in b
assert 'hoy' in b.lower()

# turno de alguien que todavía no es cliente
b = post('/turnos/nuevo', {'fecha': (hoy + timedelta(days=1)).isoformat(), 'hora': '15:00',
                           'contacto': 'Cecilia Escobar', 'telefono': '3415194903',
                           'motivo': 'Cambio de ópticas', 'estado': 'Pendiente'})
assert 'Cecilia Escobar' in b and 'mañana' in b.lower()
assert 'wa.me/5493415194903' in b, 'falta el link de WhatsApp'

# sin nombre ni cliente no se puede
assert 'de quién es el turno' in post('/turnos/nuevo', {'fecha': hoy.isoformat(), 'motivo': 'x'})
assert 'Poné la fecha' in post('/turnos/nuevo', {'fecha': '', 'contacto': 'X'})

with app.app_context():
    t_cliente = Turno.query.filter_by(cliente_id=cid).one()
    t_suelto = Turno.query.filter_by(contacto='Cecilia Escobar').one()
    tid, sid = t_cliente.id, t_suelto.id

# confirmar y cancelar
assert 'Turno confirmado' in post(f'/turnos/{sid}/estado', {'estado': 'Confirmado'})
b = post(f'/turnos/{sid}/estado', {'estado': 'Cancelado'})
assert 'Turno cancelado' in b
assert 'Cecilia' not in B(c.get('/turnos/'))            # los cancelados salen de "próximos"
assert 'Cecilia' in B(c.get('/turnos/?vista=todos'))

# vistas y búsqueda
assert patente in B(c.get('/turnos/?vista=hoy'))
assert patente not in B(c.get('/turnos/?vista=pasados'))
assert patente in B(c.get('/turnos/?q=' + patente))
assert patente not in B(c.get('/turnos/?q=zzzz'))

# editar
b = post(f'/turnos/{tid}/editar', {'fecha': hoy.isoformat(), 'hora': '11:00', 'cliente_id': cid,
                                   'vehiculo_id': vid, 'motivo': 'Service y frenos', 'estado': 'Confirmado'})
assert 'Turno guardado' in b and 'Service y frenos' in b and '11:00' in b

# el auto llega: la OT sale del turno, con el motivo y el vehículo puestos
b = B(c.get(f'/ot/nueva?turno_id={tid}'))
assert 'Viene del turno' in b and 'Service y frenos' in b and patente in b
b = post('/ot/nueva', {'turno_id': tid, 'patente': patente, 'cliente': nombre,
                       'fecha_ingreso': hoy.isoformat(), 'detalle': 'Service y frenos'})
assert 'con el turno de' in b
with app.app_context():
    t = db.session.get(Turno, tid)
    assert t.estado == 'Ingresado' and t.ot is not None
    ot_id = t.ot.id
    assert db.session.get(OrdenTrabajo, ot_id).turno_id == tid
b = B(c.get('/turnos/?vista=todos'))
assert f'OT #{ot_id}' in b
assert f'/ot/nueva?turno_id={tid}' not in b, 'el turno ya ingresó: no va más el botón'

# eliminar el cancelado
assert 'Turno eliminado' in post(f'/turnos/{sid}/eliminar')
with app.app_context():
    assert db.session.get(Turno, sid) is None
print('TODO OK')
