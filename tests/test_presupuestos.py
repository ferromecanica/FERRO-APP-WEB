"""Presupuestos: alta, trabajos, ítems, mano de obra, estados y borrado."""
import re
from wsgi import app
from app.models import Cliente, Repuesto, Presupuesto
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))
def plata(b, titulo):
    bloque = b.split('Totales')[1]
    return re.search(r'<dt>(?:<strong>)?' + titulo + r'(?:</strong>)?</dt><dd class="num">\s*(?:<strong[^>]*>)?([^<]+)', bloque).group(1).strip()

c.post('/configuracion', data={'valor_hora': '84.000'})
with app.app_context():
    cliente = Cliente.query.filter(Cliente.vehiculos.any()).first()
    cid, vid, nombre = cliente.id, cliente.vehiculos[0].id, cliente.nombre
    r = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).first()
    rid, rprecio, rcosto = r.id, r.precio_venta, r.precio_costo

# alta: hace falta cliente
assert 'Elegí el cliente' in post('/presupuestos/nuevo', {'fecha': '2026-09-19'})
b = post('/presupuestos/nuevo', {'cliente_id': cid, 'vehiculo_id': vid, 'fecha': '2026-09-19',
                                 'mostrar_precios_detalle': 'on'})
pid = int(re.search(r'Presupuesto #(\d+) creado', b).group(1))
assert pid >= 40000 and nombre in b, b[:400]

# trabajos
b = post(f'/presupuestos/{pid}/trabajos', {'descripcion': 'Reemplazo de compresor de A/A'})
assert 'Reemplazo de compresor' in b
tid = int(re.search(r'/trabajos/(\d+)/eliminar', b).group(1))

# ítems del stock y a mano
b = post(f'/presupuestos/{pid}/items', {'tipo': 'stock', 'repuesto': str(rid), 'cantidad': '2'})
assert 'del stock' in b
b = post(f'/presupuestos/{pid}/items', {'tipo': 'manual', 'descripcion': 'Gas refrigerante',
                                        'cantidad': '1', 'precio': '60.000', 'costo': '29.000'})
assert 'Gas refrigerante' in b
assert 'No encontré el repuesto' in post(f'/presupuestos/{pid}/items', {'tipo': 'stock', 'repuesto': 'nada'})
assert 'descripción y precio' in post(f'/presupuestos/{pid}/items', {'tipo': 'manual', 'descripcion': '', 'precio': ''})
assert 'mayor a cero' in post(f'/presupuestos/{pid}/items', {'tipo': 'manual', 'descripcion': 'x', 'precio': '1', 'cantidad': '0'})

# mano de obra por horas (el valor de la hora queda congelado al crear)
b = post(f'/presupuestos/{pid}/mano-obra', {'modo': 'Por horas', 'horas': '1,5', 'valor_hora': '84.000'})
rep = 2 * rprecio + 60000
costo = 2 * rcosto + 29000
total = rep + 1.5 * 84000
peso = lambda v: '$ ' + f"{v:,.0f}".replace(',', '.')
assert plata(b, 'Repuestos') == peso(rep), plata(b, 'Repuestos')
assert plata(b, 'Mano de obra') == peso(126000)
assert plata(b, 'Costo de materiales') == peso(costo)
assert plata(b, 'Ganancia') == peso(total - costo)
assert peso(total) in b

# por monto fijo
b = post(f'/presupuestos/{pid}/mano-obra', {'modo': 'Por monto', 'monto': '200.000', 'horas': '1,5'})
assert plata(b, 'Mano de obra') == peso(200000)

# editar y quitar un ítem
b = B(c.get(f'/presupuestos/{pid}'))
iid = int(re.search(r'id="item-(\d+)"', b).group(1))
b = post(f'/presupuestos/items/{iid}/editar', {'cantidad': '3', 'precio': '1.000', 'costo': '500', 'descripcion': 'Editado'})
assert 'Editado' in b and '$ 3.000' in b
assert 'Editado' not in post(f'/presupuestos/items/{iid}/eliminar')

# switch de precios en el PDF
b = post(f'/presupuestos/{pid}/precios', {'mostrar': '0'})
assert 'sin precios' in b
b = post(f'/presupuestos/{pid}/precios', {'mostrar': '1'})
assert 'precio de cada ítem' in b

# aviso cuando faltan los trabajos
assert 'Falta cargar los trabajos' not in b
b = post(f'/presupuestos/trabajos/{tid}/eliminar')
assert 'Falta cargar los trabajos' in b
post(f'/presupuestos/{pid}/trabajos', {'descripcion': 'Reemplazo de compresor de A/A'})
tid = int(re.search(r'/trabajos/(\d+)/eliminar', B(c.get(f'/presupuestos/{pid}'))).group(1))

# estados: aprobado deja de ser editable
assert 'Presupuesto aprobado' in post(f'/presupuestos/{pid}/estado', {'estado': 'Aprobado'})
for url, datos in [(f'/presupuestos/{pid}/trabajos', {'descripcion': 'no va'}),
                   (f'/presupuestos/{pid}/items', {'tipo': 'manual', 'descripcion': 'no va', 'precio': '1'}),
                   (f'/presupuestos/{pid}/mano-obra', {'modo': 'Por monto', 'monto': '1'}),
                   (f'/presupuestos/trabajos/{tid}/eliminar', None),
                   (f'/presupuestos/{pid}/cabecera', {'cliente_id': cid})]:
    b = post(url, datos)
    assert 'aprobado: no se puede modificar' in b or 'ya no se puede modificar' in b, url
assert 'no va' not in b and 'Reemplazo de compresor' in b

# listado y filtros
b = B(c.get('/presupuestos/'))
assert f'#{pid}' in b or str(pid) in b
assert str(pid) in B(c.get(f'/presupuestos/?q={pid}'))
assert str(pid) in B(c.get('/presupuestos/?estado=Aprobado'))
assert str(pid) not in B(c.get('/presupuestos/?estado=Rechazado'))

# archivar: sale del listado pero sigue estando
b = post(f'/presupuestos/{pid}/archivar', {'archivar': '1'})
assert f'#{pid} archivado' in b and 'Archivados (1)' in b
assert str(pid) not in B(c.get('/presupuestos/'))
assert str(pid) in B(c.get('/presupuestos/?estado=Archivados'))
assert str(pid) not in B(c.get('/presupuestos/?estado=Aprobado'))
b = post(f'/presupuestos/{pid}/archivar', {'archivar': '0'})
assert 'desarchivado' in b
assert str(pid) in B(c.get('/presupuestos/'))

# vuelve a Borrador y se elimina
post(f'/presupuestos/{pid}/estado', {'estado': 'Borrador'})
assert f'Presupuesto #{pid} eliminado' in post(f'/presupuestos/{pid}/eliminar')
with app.app_context():
    from app.extensions import db
    assert db.session.get(Presupuesto, pid) is None
print('TODO OK')
