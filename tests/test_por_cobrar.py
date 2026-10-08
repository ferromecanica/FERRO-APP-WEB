"""Cerrar una OT que queda por cobrar: cuánto se arregló con el cliente."""
from datetime import date
from wsgi import app
from app.extensions import db
from app.models import CondicionPago, OrdenTrabajo, Venta
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))

with app.app_context():
    ot = OrdenTrabajo.query.filter(OrdenTrabajo.estado != 'Finalizada').first()
    otid = ot.id
    assert ot.cliente is not None, 'la prueba necesita una OT con cliente'
    efectivo = str(CondicionPago.query.filter_by(nombre='Efectivo').one().id)

# ── Al cerrar sin cobrar se anota lo que se arregló ──
b = post(f'/ot/{otid}/cerrar', {'cobrado': 'no', 'clasificacion': 'Otro', 'monto_acordado': '450.000',
                                'fecha_fin': date.today().isoformat()})
assert 'Queda por cobrar: $450.000' in b, b[b.find('Queda por cobrar') - 40:][:120]
with app.app_context():
    ot = db.session.get(OrdenTrabajo, otid)
    assert ot.monto_acordado == 450000 and ot.por_cobrar
    assert ot.total_cobrado is None, 'todavía no se cobró nada'

# ── Se ve en la ficha, en la banda de estado y en el listado, para no olvidarse ──
b = B(c.get(f'/ot/{otid}'))
assert 'Acordado' in b and '450.000' in b
assert 'acordado' in b.split('Por cobrar')[1][:120], 'la banda de arriba sigue mostrando el calculado'
b = B(c.get('/ot/?estado=por_cobrar'))
assert '450.000' in b and 'a cobrar' in b, 'el listado no muestra lo acordado'

# ── Y es lo que sugiere el día que se cobra, aunque el calculado haya cambiado ──
with app.app_context():
    ot = db.session.get(OrdenTrabajo, otid)
    calculado = ot.horas_insumidas * 0 + ot.total_repuestos   # el valor hora no importa acá
b = B(c.get(f'/ot/{otid}'))
assert 'data-sugerido="450000' in b.replace('450000.0', '450000'), 'no sugiere lo acordado al cobrar'
assert 'Lo acordado al cerrar la OT fue' in b

# ── Cobrarla registra la venta por lo que realmente se cobró ──
with app.app_context():
    ventas_antes = Venta.query.count()
post(f'/ot/{otid}/cobrar', {'pago_condicion_1': efectivo, 'pago_total_1': '450.000',
                            'fecha_cobro': date.today().isoformat()})
with app.app_context():
    ot = db.session.get(OrdenTrabajo, otid)
    assert Venta.query.count() == ventas_antes + 1
    assert ot.total_cobrado == 450000 and not ot.por_cobrar
    assert ot.monto_acordado == 450000, 'lo acordado queda como quedó, es historia de la OT'

# ── Reabrir la OT borra el acuerdo junto con el resto del cierre ──
post(f'/ot/{otid}/reabrir')
with app.app_context():
    ot = db.session.get(OrdenTrabajo, otid)
    assert ot.monto_acordado is None and ot.total_cobrado is None and ot.abierta

# ── Sin poner monto igual se puede cerrar: no es obligatorio ──
b = post(f'/ot/{otid}/cerrar', {'cobrado': 'no', 'clasificacion': 'Otro',
                                'fecha_fin': date.today().isoformat()})
assert 'Queda por cobrar.' in b
with app.app_context():
    assert db.session.get(OrdenTrabajo, otid).monto_acordado is None

print('POR COBRAR OK')
