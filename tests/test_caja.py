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

# ── La apertura es un ajuste que suma: lo que ya había el primer día ──
post('/administracion/caja/nuevo', {'tipo': 'Ajuste', 'monto': '50.000', 'concepto': 'Apertura'})
with app.app_context():
    assert caja.saldo() == 50000, caja.saldo()

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

# ── Un ajuste en negativo saca plata y NO es gasto del mes ──
post('/administracion/caja/nuevo', {'tipo': 'Ajuste', 'monto': '-40.000', 'concepto': 'Depósito al banco'})
post('/administracion/caja/nuevo', {'tipo': 'Ajuste', 'monto': '-8.000', 'concepto': 'Retiro de Lucio'})
with app.app_context():
    assert caja.saldo() == 60000, caja.saldo()
    for m in MovimientoCaja.query.filter_by(tipo='Ajuste').all():
        assert m.movimiento is None, 'un ajuste no es un gasto: la plata cambia de lugar'
    r = caja.resumen()
    assert r['gastos'] == 12000 and r['ajustes'] == 2000, r   # +50.000 − 40.000 − 8.000

# ── El extracto: del más nuevo al más viejo, con el saldo de cada punto ──
with app.app_context():
    filas = caja.movimientos()
    assert len(filas) == 5, filas                      # apertura + venta + gasto + banco + retiro
    assert filas[0]['saldo'] == 60000, 'la primera fila es la última que pasó'
    assert filas[-1]['tipo'] in ('Ajuste', 'Venta'), 'la última es la más vieja'
    venta = next(f for f in filas if f['venta_id'])
    assert venta['monto'] == 70000 and venta['movimiento'] is None, 'la venta no se borra desde la caja'

b = B(c.get('/administracion/caja'))
assert 'Caja chica' in b and '$ 60.000' in b
assert 'Tornillería' in b and 'Depósito al banco' in b

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

# ── Agrupada por mes: no es una sábana infinita ──
with app.app_context():
    from app.services.performance import _restar_meses
    anterior = _restar_meses(HOY, 1).replace(day=10)
    mes_ant, mes_hoy = f'{anterior:%Y-%m}', f'{HOY:%Y-%m}'

post('/administracion/caja/nuevo', {'tipo': 'Gasto', 'monto': '1.000', 'concepto': 'Del mes pasado',
                                    'fecha': anterior.isoformat()})
with app.app_context():
    viejo, nuevo = caja.del_mes(mes_ant), caja.del_mes(mes_hoy)
    assert all(f['fecha'].strftime('%Y-%m') == mes_ant for f in viejo['filas']), 'se colaron filas de otro mes'
    # Lo que quedaba al cerrar un mes es con lo que arranca el siguiente
    assert nuevo['inicial'] == viejo['final'], (viejo['final'], nuevo['inicial'])
    assert nuevo['final'] == caja.saldo(), 'el mes en curso termina en el saldo de hoy'
    assert mes_ant in caja.meses_con_movimiento() and mes_hoy in caja.meses_con_movimiento()

# Los meses están todos en la pantalla, y se abre el que se pide
b = B(c.get(f'/administracion/caja?mes={mes_ant}'))
assert 'Del mes pasado' in b and 'De mañana' in b, 'faltan movimientos en la pantalla'
assert f'id="mes-{mes_ant}" open' in b, 'no abrió el mes que se pidió'
assert f'id="mes-{mes_hoy}" open' not in b, 'abrió un mes que no se pidió'
# Cada fila cuelga de su mes, no de cualquiera
import re as _re
tramo_viejo = b.split(f'id="mes-{mes_ant}"')[1].split('</details>')[0]
assert 'Del mes pasado' in tramo_viejo and 'De mañana' not in tramo_viejo, 'una fila quedó en el mes equivocado'

# ── Un ajuste se puede cargar en negativo, que es como se saca plata ──
with app.app_context():
    antes = caja.saldo()
post('/administracion/caja/nuevo', {'tipo': 'Ajuste', 'monto': '$ -5.000', 'concepto': 'Al banco'})
with app.app_context():
    assert caja.saldo() == antes - 5000, caja.saldo()
# Un gasto en negativo igual resta: no se puede gastar en menos
post('/administracion/caja/nuevo', {'tipo': 'Gasto', 'monto': '-2.000', 'concepto': 'Escrito al revés'})
with app.app_context():
    assert caja.saldo() == antes - 7000, caja.saldo()

# ── Corregir un movimiento del mes en curso ──
with app.app_context():
    gid2 = MovimientoCaja.query.filter_by(concepto='De mañana').one().id
post(f'/administracion/caja/{gid2}/editar', {'tipo': 'Gasto', 'monto': '7.000',
                                             'concepto': 'De mañana, bien', 'fecha': HOY.isoformat()})
with app.app_context():
    m = db.session.get(MovimientoCaja, gid2)
    assert m.monto == 7000 and m.concepto == 'De mañana, bien' and m.fecha == HOY, (m.monto, m.fecha)
    assert m.movimiento.total == 7000, 'el egreso no siguió al gasto'
    assert m.movimiento.fecha == HOY and 'De mañana, bien' in m.movimiento.concepto

# De gasto a ajuste: el egreso tiene que desaparecer, porque deja de ser gasto del mes
with app.app_context():
    mid2 = db.session.get(MovimientoCaja, gid2).movimiento_id
post(f'/administracion/caja/{gid2}/editar', {'tipo': 'Ajuste', 'monto': '-7.000',
                                             'concepto': 'Era un depósito', 'fecha': HOY.isoformat()})
with app.app_context():
    m = db.session.get(MovimientoCaja, gid2)
    assert m.tipo == 'Ajuste' and m.monto == -7000, (m.tipo, m.monto)
    assert m.movimiento is None and db.session.get(MovimientoContable, mid2) is None, 'quedó un egreso huérfano'

# Y de vuelta a gasto: el egreso tiene que volver
post(f'/administracion/caja/{gid2}/editar', {'tipo': 'Gasto', 'monto': '7.000',
                                             'concepto': 'Era un gasto nomás', 'fecha': HOY.isoformat()})
with app.app_context():
    m = db.session.get(MovimientoCaja, gid2)
    assert m.movimiento is not None and m.movimiento.total == 7000, 'no volvió a generar el egreso'
    assert m.movimiento.tipo == 'Egreso' and m.movimiento.mes_imputacion == f'{HOY:%Y-%m}'

# Sin monto no se guarda nada
assert 'Poné cuánta plata' in post(f'/administracion/caja/{gid2}/editar',
                                  {'tipo': 'Gasto', 'monto': '', 'concepto': 'x'})
with app.app_context():
    assert db.session.get(MovimientoCaja, gid2).concepto == 'Era un gasto nomás'

# ── Los meses salen uno abajo del otro, con el arrastre encadenado ──
with app.app_context():
    meses = caja.por_mes()
    assert [m['mes'] for m in meses] == sorted([m['mes'] for m in meses], reverse=True), 'el más nuevo va arriba'
    for mas_viejo, mas_nuevo in zip(meses[1:], meses[:-1]):
        assert mas_viejo['final'] == mas_nuevo['inicial'], (mas_viejo['mes'], mas_nuevo['mes'])
    assert meses[0]['final'] == caja.saldo(), 'el último mes tiene que terminar en el saldo de hoy'
    assert meses[-1]['inicial'] == 0, 'el primer mes arranca de cero'

b = B(c.get('/administracion/caja'))
with app.app_context():
    for m in caja.por_mes():
        assert f'id="mes-{m["mes"]}"' in b, f'falta el mes {m["mes"]} en la pantalla'

# ── Un mes cerrado no se toca ──
with app.app_context():
    from app.models import CierreMensual
    db.session.add(CierreMensual(mes=mes_ant, estado='Cerrado'))
    db.session.commit()
    viejo = MovimientoCaja.query.filter_by(concepto='Del mes pasado').one().id
assert 'ya está cerrado' in post(f'/administracion/caja/{viejo}/eliminar')
assert 'ya está cerrado' in post(f'/administracion/caja/{viejo}/editar',
                                {'tipo': 'Gasto', 'monto': '1', 'concepto': 'no'})
with app.app_context():
    quedo = db.session.get(MovimientoCaja, viejo)
    assert quedo is not None, 'borró un movimiento de un mes cerrado'
    assert quedo.concepto == 'Del mes pasado' and quedo.monto == 1000, 'editó un mes cerrado'

# Tampoco se puede meter una fila nueva adentro de un mes cerrado moviéndole la fecha
with app.app_context():
    suelto = MovimientoCaja.query.filter_by(concepto='Era un gasto nomás').one().id
assert 'ya está cerrado' in post(f'/administracion/caja/{suelto}/editar',
                                {'tipo': 'Gasto', 'monto': '7.000', 'concepto': 'Era un gasto nomás',
                                 'fecha': anterior.isoformat()})
with app.app_context():
    assert db.session.get(MovimientoCaja, suelto).fecha == HOY, 'se mudó a un mes cerrado'

print('CAJA OK')
