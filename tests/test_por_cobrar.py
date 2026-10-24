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
    transferencia = str(CondicionPago.query.filter_by(nombre='Transferencia').one().id)

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
    from app.models import MovimientoContable, Venta
    modelo = db.session.get(OrdenTrabajo, otid)
    otra = OrdenTrabajo(id=OrdenTrabajo.proximo_numero(), vehiculo_id=modelo.vehiculo_id,
                        cliente_id=modelo.cliente_id, estado='En proceso',
                        detalle='Distribución y portón de baúl')
    db.session.add(otra)
    db.session.commit()
    oid2 = otra.id
    ventas_antes = Venta.query.count()

post(f'/ot/{oid2}/cerrar', {'cobrado': 'no', 'clasificacion': 'Otro', 'monto_acordado': '400.000',
                            'fecha_fin': '2026-10-01'})

# Paga 200.000 de los 400.000: la OT sigue por cobrar, con saldo
b = post(f'/ot/{oid2}/cobrar', {'pago_condicion_1': efectivo, 'pago_total_1': '200.000',
                                'fecha_cobro': '2026-10-05'})
assert 'Quedan $200.000 por cobrar' in b, b[b.find('Cobro registrado'):][:140]
with app.app_context():
    o = db.session.get(OrdenTrabajo, oid2)
    assert o.total_cobrado == 200000 and o.saldo == 200000 and o.por_cobrar
    assert len(o.ventas) == 1, 'el primer pago es su propia venta'
    primera = o.ventas[0].id

# Cada pago es una venta aparte, en su mes
b = post(f'/ot/{oid2}/cobrar', {'pago_condicion_1': efectivo, 'pago_total_1': '150.000',
                                'fecha_cobro': '2026-11-03'})
assert 'Quedan $50.000 por cobrar' in b
with app.app_context():
    o = db.session.get(OrdenTrabajo, oid2)
    assert o.total_cobrado == 350000 and o.saldo == 50000 and o.por_cobrar
    assert len(o.ventas) == 2, 'el segundo pago tiene que ser otra venta'
    assert [v.bruto_cobrado for v in o.ventas] == [200000, 150000]
    assert all(v.ot_id == oid2 for v in o.ventas), 'cada venta queda atada a la OT'
    # Lo importante: la venta de octubre no se tocó al cobrar en noviembre
    vieja = db.session.get(Venta, primera)
    assert vieja.bruto_cobrado == 200000 and f'{vieja.fecha:%Y-%m}' == '2026-10'
    meses = sorted(m.mes_imputacion for m in MovimientoContable.query.filter(
        MovimientoContable.venta_id.in_([v.id for v in o.ventas])))
    assert meses == ['2026-10', '2026-11'], meses

# El último pago la salda
post(f'/ot/{oid2}/cobrar', {'pago_condicion_1': efectivo, 'pago_total_1': '50.000',
                            'fecha_cobro': '2026-11-10'})
with app.app_context():
    o = db.session.get(OrdenTrabajo, oid2)
    assert o.total_cobrado == 400000 and o.saldo == 0 and not o.por_cobrar
    assert len(o.ventas) == 3 and Venta.query.count() == ventas_antes + 3
    # El costo de los materiales se reparte, pero suma el real una sola vez
    costo_puesto = sum((i.costo_unitario or 0) * (i.cantidad or 0) for v in o.ventas for i in v.items)
    assert abs(costo_puesto - o.costo_repuestos) < 0.05, (costo_puesto, o.costo_repuestos)
    assert sum(v.bruto_cobrado for v in o.ventas) == 400000

# Ya saldada, no deja cobrar de nuevo
assert 'no tiene un cobro pendiente' in post(f'/ot/{oid2}/cobrar',
                                             {'pago_condicion_1': efectivo, 'pago_total_1': '1.000'})

# ── Lo que se paga en efectivo entra a la caja chica, pago por pago ──
with app.app_context():
    from app.services import caja
    o = db.session.get(OrdenTrabajo, oid2)
    enlacaja = [f for f in caja.movimientos() if f['venta_id'] in [v.id for v in o.ventas]]
    assert len(enlacaja) == 3, 'cada pago en efectivo tiene que entrar a la caja'
    assert sorted(f['monto'] for f in enlacaja) == [50000, 150000, 200000]
    assert sorted(str(f['fecha']) for f in enlacaja) == ['2026-10-05', '2026-11-03', '2026-11-10'], \
        'cada pago entra a la caja el día que se cobró'

# ── Y si un pago es mitad efectivo y mitad transferencia, solo va el efectivo ──
with app.app_context():
    modelo = db.session.get(OrdenTrabajo, otid)
    mixta = OrdenTrabajo(id=OrdenTrabajo.proximo_numero(), vehiculo_id=modelo.vehiculo_id,
                         cliente_id=modelo.cliente_id, estado='En proceso', detalle='Pago mixto')
    db.session.add(mixta)
    db.session.commit()
    oid3 = mixta.id
    caja_antes = caja.entradas_por_ventas()

post(f'/ot/{oid3}/cerrar', {'cobrado': 'no', 'clasificacion': 'Otro', 'monto_acordado': '300.000',
                            'fecha_fin': '2026-10-01'})
post(f'/ot/{oid3}/cobrar', {'pago_condicion_1': efectivo, 'pago_total_1': '80.000',
                            'pago_condicion_2': transferencia, 'pago_total_2': '20.000',
                            'fecha_cobro': '2026-10-20'})
with app.app_context():
    o = db.session.get(OrdenTrabajo, oid3)
    assert o.total_cobrado == 100000 and o.saldo == 200000, (o.total_cobrado, o.saldo)
    assert caja.entradas_por_ventas() == caja_antes + 80000, 'a la caja va solo la parte en efectivo'
    assert sorted(p.destino for p in o.cobros) == ['Banco', 'Caja']

# ── Lo que pagó a medias sigue apareciendo en el listado y en el Tablero ──
# Antes, en cuanto entraba el primer pago la OT ya tenía una venta y las dos
# consultas la dejaban afuera: desaparecía justo la que había que ir a cobrar.
with app.app_context():
    a_medias = db.session.get(OrdenTrabajo, oid3)   # pagó 100.000 de 300.000
    assert a_medias.por_cobrar and a_medias.ventas, 'la prueba necesita una OT pagada a medias'
    porsql = OrdenTrabajo.query.filter(OrdenTrabajo.filtro_por_cobrar()).all()
    porpropiedad = [o for o in OrdenTrabajo.query.all() if o.por_cobrar]
    assert {o.id for o in porsql} == {o.id for o in porpropiedad}, 'el filtro no dice lo mismo que la OT'
    assert oid3 in {o.id for o in porsql}, 'la pagada a medias se cayó del filtro'
    assert a_medias.falta_cobrar == 200000, a_medias.falta_cobrar

b = B(c.get('/ot/?estado=por_cobrar'))
assert f'>{oid3}<' in b.replace(' ', ''), 'el listado Por cobrar no muestra la pagada a medias'

b = B(c.get('/'))
assert 'Por cobrar' in b, 'el Tablero tiene que mostrar la tarjeta'
with app.app_context():
    cuantas = OrdenTrabajo.query.filter(OrdenTrabajo.filtro_por_cobrar()).count()
assert f'{cuantas} OT' in b, f'el Tablero no cuenta las {cuantas} por cobrar'

# En Ventas se ve cada pago, atado a su OT
b = B(c.get('/ventas/'))
assert f'OT #{oid2}' in b and '2º pago' in b, 'el listado de ventas no distingue los pagos'
assert 'de 3' not in b, 'no se puede saber de antemano cuántos pagos va a hacer el cliente'

# ── Una venta de OT no se anula desde Ventas: se maneja desde la OT ──
with app.app_context():
    vid = db.session.get(OrdenTrabajo, oid2).ventas[0].id
assert 'se maneja desde la OT' in post(f'/ventas/{vid}/anular')

# ── Reabrir la OT se lleva las tres ventas ──
post(f'/ot/{oid2}/reabrir')
with app.app_context():
    o = db.session.get(OrdenTrabajo, oid2)
    assert o.abierta and not o.ventas and o.total_cobrado is None and o.monto_acordado is None
    assert Venta.query.filter_by(ot_id=oid2).count() == 0, 'quedaron ventas de una OT reabierta'
    assert MovimientoContable.query.filter_by(venta_id=vid).count() == 0

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
