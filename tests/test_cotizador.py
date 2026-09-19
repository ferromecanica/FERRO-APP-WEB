"""Cotizador: ítems del stock o a mano, mano de obra y resultado."""
import re
from wsgi import app
from app.extensions import db
from app.models import ConfigTaller, Repuesto
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))
def numeros(b):
    bloque = b.split('Resultado')[1]
    return {k: v for k, v in re.findall(r'<dt>(?:<strong>)?([^<]+)(?:</strong>)?</dt><dd class="num">([^<]+)', bloque)}
c.post('/configuracion', data={'valor_hora': '84.000'})
with app.app_context():
    r = Repuesto.query.filter(Repuesto.id != 99).first(); rid, rprecio, rcosto = r.id, r.precio_venta, r.precio_costo
# del stock
b = post('/cotizador/items', {'tipo': 'stock', 'repuesto': str(rid), 'cantidad': '2'})
assert 'del stock' in b
# a mano
b = post('/cotizador/items', {'tipo': 'manual', 'descripcion': 'Pastillas delanteras', 'cantidad': '1', 'precio': '60.000', 'costo': '29.000'})
assert 'Pastillas delanteras' in b
# errores
assert 'No encontré el repuesto' in post('/cotizador/items', {'tipo': 'stock', 'repuesto': 'nada'})
assert 'descripción y precio' in post('/cotizador/items', {'tipo': 'manual', 'descripcion': '', 'precio': ''})
# mano de obra por horas
b = post('/cotizador/mano-obra', {'modo_mo': 'horas', 'horas': '1,5'})
esperado_rep = 2 * rprecio + 60000
esperado_costo = 2 * rcosto + 29000
total = esperado_rep + 1.5 * 84000
n = numeros(b)
assert n['Repuestos'].strip().endswith(f"{esperado_rep:,.0f}".replace(',', '.')), n
assert '126.000' in n['Mano de obra'], n
assert f"{total:,.0f}".replace(',', '.') in b and f"{total - esperado_costo:,.0f}".replace(',', '.') in b
# por monto fijo
b = post('/cotizador/mano-obra', {'modo_mo': 'monto', 'monto_mo': '200.000', 'horas': '1,5'})
assert '200.000' in numeros(b)['Mano de obra']
# editar y quitar
b = B(c.get('/cotizador/'))
iid = int(re.search(r'id="coti-(\d+)"', b).group(1))
b = post(f'/cotizador/items/{iid}/editar', {'cantidad': '3', 'precio': '1.000', 'costo': '500', 'descripcion': 'Editado'})
assert 'Editado' in b and '$ 3.000' in b
b = post(f'/cotizador/items/{iid}/eliminar')
assert 'Editado' not in b
# vaciar
b = post('/cotizador/limpiar')
assert 'Cotización vaciada' in b and 'Pastillas delanteras' not in b
print('TODO OK')

# pasar a presupuesto
from app.models import Cliente
with app.app_context():
    cliente = Cliente.query.filter(Cliente.vehiculos.any()).first()
    cid, vid = cliente.id, cliente.vehiculos[0].id
assert 'está vacía' in post('/cotizador/pasar-a-presupuesto', {'cliente_id': cid, 'trabajos': 'Service'})
post('/cotizador/items', {'tipo': 'manual', 'descripcion': 'Filtro de aceite', 'cantidad': '2', 'precio': '10.000', 'costo': '6.000'})
post('/cotizador/mano-obra', {'modo_mo': 'horas', 'horas': '2'})
assert 'Elegí el cliente' in post('/cotizador/pasar-a-presupuesto', {'trabajos': 'Service'})
assert 'Escribí los trabajos' in post('/cotizador/pasar-a-presupuesto', {'cliente_id': cid, 'trabajos': '  \n - \n'})
b = post('/cotizador/pasar-a-presupuesto', {'cliente_id': cid, 'vehiculo_id': vid,
                                            'trabajos': 'Service completo\n- Cambio de filtro de aceite\n\n'})
assert 'creado con lo cotizado' in b and 'Filtro de aceite' in b and '$ 20.000' in b
assert 'Service completo' in b and 'Cambio de filtro de aceite' in b and 'Falta cargar los trabajos' not in b
assert '168.000' in b   # 2 h x 84.000
assert 'Filtro de aceite' not in B(c.get('/cotizador/'))   # el cotizador quedó vacío
print('PASAR A PRESUPUESTO OK')
