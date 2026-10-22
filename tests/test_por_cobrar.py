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
assert 'data-sugerido="450000' in b.replace('450000.0', '450000'), 'no sugiere lo que falta cobrar'
assert 'Acordado' in b and 'Falta' in b, 'el cobro no muestra la cuenta de cuánto falta'

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

# ── Pagos parciales: el cliente deja una parte y completa después ──
with app.app_context():
    from app.models import MovimientoContable
    modelo = db.session.get(OrdenTrabajo, otid)
    otra = OrdenTrabajo(id=OrdenTrabajo.proximo_numero(), vehiculo_id=modelo.vehiculo_id,
                        cliente_id=modelo.cliente_id, estado='En proceso',
                        detalle='Distribución y portón de baúl')
    db.session.add(otra)
    db.session.commit()
    oid2 = otra.id
    movs_antes = MovimientoContable.query.count()

post(f'/ot/{oid2}/cerrar', {'cobrado': 'no', 'clasificacion': 'Otro', 'monto_acordado': '400.000',
                            'fecha_fin': date.today().isoformat()})

# Paga 200.000 de los 400.000: la OT sigue por cobrar, con saldo
b = post(f'/ot/{oid2}/cobrar', {'pago_condicion_1': efectivo, 'pago_total_1': '200.000',
                                'fecha_cobro': '2026-10-05'})
assert 'Quedan $200.000 por cobrar' in b, b[b.find('Cobro registrado'):][:140]
with app.app_context():
    o = db.session.get(OrdenTrabajo, oid2)
    assert o.total_cobrado == 200000 and o.saldo == 200000
    assert o.por_cobrar, 'con saldo pendiente tiene que seguir por cobrar'
    assert len(o.venta.pagos) == 1

# Se puede volver a entrar y agregar otro pago
b = post(f'/ot/{oid2}/cobrar', {'pago_condicion_1': efectivo, 'pago_total_1': '150.000',
                                'fecha_cobro': '2026-11-03'})
assert 'Quedan $50.000 por cobrar' in b
with app.app_context():
    o = db.session.get(OrdenTrabajo, oid2)
    assert o.total_cobrado == 350000 and o.saldo == 50000 and o.por_cobrar
    assert len(o.venta.pagos) == 2, 'el segundo pago tiene que sumarse, no reemplazar'
    assert o.venta.bruto_cobrado == 350000
    # Cada pago cuenta el mes en que entró
    meses = sorted(m.mes_imputacion for m in MovimientoContable.query.filter_by(venta_id=o.venta.id))
    assert meses == ['2026-10', '2026-11'], meses
    totales = sorted(m.total for m in MovimientoContable.query.filter_by(venta_id=o.venta.id))
    assert totales == [150000, 200000], totales

# El último pago la salda y sale de la lista de por cobrar
b = post(f'/ot/{oid2}/cobrar', {'pago_condicion_1': efectivo, 'pago_total_1': '50.000',
                                'fecha_cobro': '2026-11-10'})
assert 'Quedan' not in b.split('Cobro registrado')[1][:80]
with app.app_context():
    o = db.session.get(OrdenTrabajo, oid2)
    assert o.total_cobrado == 400000 and o.saldo == 0 and not o.por_cobrar
    assert len(o.venta.pagos) == 3
    # El costo de los materiales se cuenta una sola vez
    assert len(o.venta.items) == 1 and o.venta.items[0].precio_unitario == 400000

# Ya saldada, no deja cobrar de nuevo
assert 'no tiene un cobro pendiente' in post(f'/ot/{oid2}/cobrar',
                                             {'pago_condicion_1': efectivo, 'pago_total_1': '1.000'})

# ── Una venta de OT no se anula desde Ventas: se maneja desde la OT ──
with app.app_context():
    vid = db.session.get(OrdenTrabajo, oid2).venta.id
assert 'se maneja desde la OT' in post(f'/ventas/{vid}/anular')

# ── Reabrir la OT se lleva la venta entera, con sus tres pagos ──
post(f'/ot/{oid2}/reabrir')
with app.app_context():
    o = db.session.get(OrdenTrabajo, oid2)
    assert o.abierta and not o.ventas and o.total_cobrado is None and o.monto_acordado is None
    assert MovimientoContable.query.filter_by(venta_id=vid).count() == 0, 'quedaron ingresos de una venta borrada'

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
