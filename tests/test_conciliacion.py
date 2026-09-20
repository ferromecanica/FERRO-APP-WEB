"""El taller y la administración enganchados: cada venta cobrada deja su ingreso."""
from datetime import date
from wsgi import app
from app.extensions import db
from app.models import Cliente, CondicionPago, MovimientoContable, OrdenTrabajo, Repuesto, Venta
from app.services import contable
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))
# Las formas de pago ahora son filas de CondicionPago (traen la comisión de la tarjeta)
def condicion(nombre):
    with app.app_context():
        return str(CondicionPago.query.filter_by(nombre=nombre).one().id)


MES = date.today().strftime('%Y-%m')

with app.app_context():
    ot = OrdenTrabajo.query.filter_by(estado='En proceso').first()
    assert ot is not None, 'la demo tiene que traer una OT abierta'
    otid, cliente_ot = ot.id, (ot.cliente.nombre if ot.cliente else None)
    cliente = Cliente.query.first(); cid, cnombre = cliente.id, cliente.nombre
    r = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).first()
    r.stock_actual = 10; db.session.commit()
    rid = r.id

# ── Cerrar una OT cobrando: nace el ingreso, atado a la venta ──
post(f'/ot/{otid}/cerrar', {'cobrado': 'si', 'clasificacion': 'Otro', 'total_cobrado': '250.000',
                            'condicion_id': condicion('Efectivo'), 'fecha_fin': date.today().isoformat(),
                            'cliente_id': cid})
with app.app_context():
    venta = Venta.query.filter_by(ot_id=otid).one()
    mov = MovimientoContable.query.filter_by(venta_id=venta.id).one()
    assert mov.tipo == 'Ingreso' and mov.clasificacion == 'Ventas'
    assert mov.total == 250000, mov.total
    assert mov.cobrado and mov.automatico
    assert mov.mes_imputacion == MES
    assert f'OT:{otid}' in mov.concepto, mov.concepto
    movid, vid = mov.id, venta.id

# el ingreso automático no se edita ni se borra a mano
assert 'salió de una venta' in B(c.get(f'/administracion/{movid}/editar', follow_redirects=True))
assert 'no se borra desde acá' in post(f'/administracion/{movid}/eliminar')

# aparece en la pantalla de movimientos, apuntando a su venta
b = B(c.get(f'/administracion/?mes={MES}'))
assert f'venta {vid}' in b and '$ 250.000' in b

# ── Reabrir la OT: se va la venta y también el ingreso ──
post(f'/ot/{otid}/reabrir')
with app.app_context():
    assert db.session.get(Venta, vid) is None
    assert db.session.get(MovimientoContable, movid) is None, 'quedó el ingreso de una venta que ya no existe'

# ── Mostrador: cobrar deja el ingreso; anular lo saca ──
post('/ventas/mostrador/items', {'tipo': 'manual', 'descripcion': 'Revisión pre-compra',
                                 'precio': '80.000', 'costo': '0'})
post('/ventas/mostrador/cobrar', {'condicion_id': condicion('Transferencia'), 'cliente_id': cid,
                                  'fecha': date.today().isoformat()})
with app.app_context():
    venta = Venta.query.filter_by(ot_id=None).order_by(Venta.id.desc()).first()
    mov = MovimientoContable.query.filter_by(venta_id=venta.id).one()
    assert mov.total == 80000 and mov.quien == cnombre
    assert 'Revisión pre-compra' in mov.concepto
    vid, movid = venta.id, mov.id

post(f'/ventas/{vid}/anular')
with app.app_context():
    assert db.session.get(MovimientoContable, movid) is None, 'la venta anulada dejó su ingreso'

# ── Una venta cargada sin pasar por la app queda marcada, y se carga de un click ──
with app.app_context():
    from app.models import VentaItem
    suelta = Venta(fecha=date.today(), cliente_id=cid, metodo_pago='Efectivo')
    suelta.items.append(VentaItem(descripcion='Venta vieja sin ingreso', cantidad=1,
                                  precio_unitario=123456, costo_unitario=0))
    db.session.add(suelta); db.session.commit()
    sid = suelta.id
    faltantes = [v.id for v in contable.ventas_sin_ingreso(MES)]
    assert sid in faltantes, 'no detectó la venta sin ingreso'

b = B(c.get(f'/administracion/?mes={MES}'))
assert 'no dicen lo mismo' in b and '$ 123.456' in b and 'Cargar el ingreso' in b
assert 'Facturado en Ventas' in b, 'falta el cuadre del mes'

b = post(f'/administracion/ventas/{sid}/ingreso')
assert 'Ingreso cargado' in b
with app.app_context():
    mov = MovimientoContable.query.filter_by(venta_id=sid).one()
    assert mov.total == 123456
    assert not contable.ventas_sin_ingreso(MES) or sid not in [v.id for v in contable.ventas_sin_ingreso(MES)]
# ya no lo pide dos veces
assert 'ya tiene su ingreso' in post(f'/administracion/ventas/{sid}/ingreso')

# ── Lo importado de AppSheet no se marca: alcanza con que el concepto nombre la OT ──
with app.app_context():
    vieja = Venta(fecha=date.today(), cliente_id=cid, ot_id=otid, metodo_pago='Efectivo')
    vieja.items.append(VentaItem(descripcion='Trabajo', cantidad=1, precio_unitario=50000, costo_unitario=0))
    db.session.add(vieja)
    db.session.add(MovimientoContable(
        fecha=date.today(), tipo='Ingreso', mes_imputacion=MES, total=50000,
        quien=cnombre, concepto=f'Service y otros. OT:{otid}', cobrado=True))
    db.session.commit()
    assert vieja.id not in [v.id for v in contable.ventas_sin_ingreso(MES)], \
        'marcó una venta que ya estaba cargada con el número de OT en el concepto'

# ── Una venta en $0 (sin cargo) no genera ingreso ──
with app.app_context():
    sin_cargo = Venta(fecha=date.today(), cliente_id=cid)
    sin_cargo.items.append(VentaItem(descripcion='Sin cargo', cantidad=1, precio_unitario=0, costo_unitario=0))
    db.session.add(sin_cargo); db.session.commit()
    assert contable.registrar_venta(sin_cargo) is None
    assert sin_cargo.id not in [v.id for v in contable.ventas_sin_ingreso(MES)]

# ── Un mes ya cerrado no se controla: la historia quedó como quedó ──
with app.app_context():
    from app.models import CierreMensual
    suelta2 = Venta(fecha=date.today(), cliente_id=cid, metodo_pago='Efectivo')
    suelta2.items.append(VentaItem(descripcion='Otra sin ingreso', cantidad=1,
                                   precio_unitario=777, costo_unitario=0))
    db.session.add(suelta2)
    db.session.add(CierreMensual(mes=MES, estado='Cerrado'))
    db.session.commit()
    assert contable.control_del_mes(MES) is None, 'no tiene que controlar un mes cerrado'
assert 'no dicen lo mismo' not in B(c.get(f'/administracion/?mes={MES}'))

print('CONCILIACIÓN OK')
