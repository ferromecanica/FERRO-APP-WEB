import re
from wsgi import app
from app.extensions import db
from app.models import *
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
fl = lambda b: re.findall(r'class="flash[^"]*">([^<]*)', b)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))
def check(cond, b, paso):
    if not cond: raise SystemExit(f'FALLA {paso}: {fl(b)}')
def rep(i):
    with app.app_context(): r = db.session.get(Repuesto, i); db.session.expunge(r); return r
# repuestos de prueba: uno normal y uno con costo fijo
post('/stock/markups', {'proveedor': 'RSF', 'marca_envase': '', 'markup': '1,4'})
post('/stock/nuevo', {'nombre': 'Filtro A', 'proveedor': 'RSF', 'costo_lista': '1.000', 'stock_inicial': '2'})
post('/stock/nuevo', {'nombre': 'Filtro B (costo fijo)', 'proveedor': 'RSF', 'costo_lista': '500', 'costo_manual': '1'})
a, bb = 1002, 1003
assert (rep(a).precio_venta, rep(bb).precio_venta) == (1400.0, 700.0)
# cabecera
b = post('/stock/ingresos/nuevo', {'proveedor': 'Inventado', 'fecha': '2026-09-19'}); check('Elegí un proveedor' in b, b, 'proveedor inválido')
b = post('/stock/ingresos/nuevo', {'proveedor': 'RSF', 'fecha': '2026-09-19', 'nro_factura': '0010-00108189', 'notas': 'Filtros'})
check('ahora cargá los repuestos' in b, b, 'crear cabecera')
with app.app_context(): ing_id = IngresoStock.query.one().id
# ítems
b = post(f'/stock/ingresos/{ing_id}/items', {'repuesto': 'no existe', 'cantidad': '1'}); check('No encontré el repuesto' in b, b, 'repuesto inexistente')
b = post(f'/stock/ingresos/{ing_id}/items', {'repuesto': f'{a} · Filtro A', 'cantidad': '0'}); check('mayor a cero' in b, b, 'cantidad 0')
post(f'/stock/ingresos/{ing_id}/items', {'repuesto': str(a), 'cantidad': '3', 'costo_unitario': '1.200'})
post(f'/stock/ingresos/{ing_id}/items', {'repuesto': str(a), 'cantidad': '2'})          # mismo repuesto: suma
post(f'/stock/ingresos/{ing_id}/items', {'repuesto': str(bb), 'cantidad': '4', 'costo_unitario': '600'})
with app.app_context():
    ing = db.session.get(IngresoStock, ing_id)
    assert len(ing.items) == 2 and ing.items[0].cantidad == 5 and ing.items[0].costo_unitario == 1200
    assert ing.total == 5 * 1200 + 4 * 600
assert rep(a).stock_actual == 2, 'el borrador no toca el stock'
# editar y quitar un ítem
with app.app_context(): iid = IngresoStockItem.query.filter_by(repuesto_id=bb).one().id
post(f'/stock/ingresos/items/{iid}/editar', {'cantidad': '5', 'costo_unitario': '650'})
with app.app_context(): x = db.session.get(IngresoStockItem, iid); assert (x.cantidad, x.costo_unitario) == (5, 650)
b = B(c.get(f'/stock/ingresos/{ing_id}')); assert 'costo $ 1.000,00 → $ 1.200,00' in b.replace('costo ', 'costo ') or '1.200,00' in b
# confirmar
b = post(f'/stock/ingresos/{ing_id}/confirmar'); check('entraron 2 repuestos' in b and 'actualizó el costo de 1' in b, b, 'confirmar')
assert rep(a).stock_actual == 7 and rep(a).costo_lista == 1200 and rep(a).precio_venta == 1680.0, (rep(a).stock_actual, rep(a).precio_venta)
assert rep(bb).stock_actual == 5 and rep(bb).costo_lista == 500 and rep(bb).precio_venta == 700.0, 'costo fijo no cambia'
with app.app_context():
    movs = MovimientoStock.query.filter_by(ingreso_id=ing_id).all()
    assert len(movs) == 2 and all(m.tipo == 'Ingreso' for m in movs) and '0010-00108189' in movs[0].detalle
# confirmado: no se edita ni se elimina
b = post(f'/stock/ingresos/{ing_id}/items', {'repuesto': str(a), 'cantidad': '1'}); check('ya está confirmado' in b, b, 'agregar en confirmado')
b = post(f'/stock/ingresos/{ing_id}/eliminar'); check('primero anulalo' in b, b, 'eliminar confirmado')
# anular: devuelve el stock
b = post(f'/stock/ingresos/{ing_id}/anular'); check('se descontó del stock' in b, b, 'anular')
assert rep(a).stock_actual == 2 and rep(bb).stock_actual == 0
assert rep(a).costo_lista == 1200, 'el costo queda como quedó'
b = post(f'/stock/ingresos/{ing_id}/anular'); check('Solo se puede anular' in b, b, 'doble anulación')
# listado y filtros
b = B(c.get('/stock/ingresos')); assert 'RSF' in b and 'Anulado' in b
assert 'RSF' not in B(c.get('/stock/ingresos?estado=Borrador'))
# borrador se elimina
post('/stock/ingresos/nuevo', {'proveedor': 'RSF'})
with app.app_context(): otro = IngresoStock.query.filter_by(estado='Borrador').one().id
b = post(f'/stock/ingresos/{otro}/eliminar'); check('Ingreso eliminado' in b, b, 'eliminar borrador')
print('TODO OK')
