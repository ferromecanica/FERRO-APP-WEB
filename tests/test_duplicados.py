"""Control de repuestos repetidos al darlos de alta o editarlos."""
from wsgi import app
from app.extensions import db
from app.models import Repuesto
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(d): return B(c.post('/stock/nuevo', data=d, follow_redirects=True))
def cuantos():
    with app.app_context(): return Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).count()

base = {'nombre': 'AMORTIGUADOR DELANTERO IZQUIERDO CRUZE', 'marca': 'SACHS', 'nro_parte': '318 105',
        'proveedor': 'RSF', 'costo_lista': '95.579,13', 'cod_proveedor': 'SACH1'}
assert 'creado' in post(base)
antes = cuantos()
# mismo nº de parte escrito distinto (318-105)
b = post(dict(base, nombre='AMORT DEL IZQ CRUZE', nro_parte='318-105', cod_proveedor=''))
assert 'se parece' in b and 'el mismo nº de parte y la misma marca' in b and 'guardar igual' in b and cuantos() == antes
# nº de parte con un carácter de diferencia y el mismo nombre (una letra cambiada): avisa
b = post(dict(base, nombre='AMORTIGADOR DELANTERO IZQUIERDO CRUZE', nro_parte='318 106', cod_proveedor=''))
assert 'muy parecido' in b and cuantos() == antes
# ...pero si el nombre dice otra cosa (izquierdo / derecho), no molesta
b = post(dict(base, nombre='AMORTIGUADOR DELANTERO DERECHO CRUZE', nro_parte='318 106', cod_proveedor=''))
assert 'creado' in b and 'se parece' not in b
# mismo código de barras
b = post({'nombre': 'OTRA COSA', 'costo_lista': '1', 'codigo_barras': '7790001234567'})
assert 'creado' in b
b = post({'nombre': 'OTRA COSA MAS', 'costo_lista': '1', 'codigo_barras': '7790001234567'})
assert 'el mismo código de barras' in b
# mismo nombre, sin códigos
b = post({'nombre': 'AMORTIGUADOR DELANTERO IZQUIERDO CRUZE', 'costo_lista': '1'})
assert 'el mismo nombre' in b
# variantes del mismo producto (HAB, 1L / 4L) no son duplicados
assert 'creado' in post({'nombre': 'KITZZ7 HAB FILTROS MAHLE COROLLA', 'nro_parte': 'KITZZ7H', 'costo_lista': '1'})
assert 'creado' in post({'nombre': 'KITZZ7 FILTROS MAHLE COROLLA', 'nro_parte': 'KITZZ7', 'costo_lista': '1'})
assert 'se parece' not in post({'nombre': 'Helix Ultra 0W-30 1L', 'costo_lista': '1'})
# "guardar igual" lo deja pasar
antes = cuantos()
b = post(dict(base, nombre='AMORTIGADOR DELANTERO IZQUIERDO CRUZE', nro_parte='318 106', cod_proveedor='', ignorar_duplicados='1'))
assert 'creado' in b and cuantos() == antes + 1
# algo claramente distinto no molesta
b = post({'nombre': 'KIT DISTRIBUCION SKF RENAULT K4M', 'nro_parte': '06020 C/BBA', 'costo_lista': '1'})
assert 'creado' in b and 'se parece' not in b
# al editar un repuesto no se avisa de sí mismo
with app.app_context(): rid = Repuesto.query.filter_by(nro_parte='06020 C/BBA').one().id
b = B(c.post(f'/stock/{rid}', data={'nombre': 'KIT DISTRIBUCION SKF RENAULT K4M (C/BBA)', 'nro_parte': '06020 C/BBA', 'costo_lista': '2'}, follow_redirects=True))
assert 'guardado' in b and 'se parece' not in b
# pero sí del que quedó con el nombre casi igual
with app.app_context(): rid = Repuesto.query.filter_by(nro_parte='318 105').one().id
assert 'muy parecido' in B(c.post(f'/stock/{rid}', data=base, follow_redirects=True))
print('TODO OK')
