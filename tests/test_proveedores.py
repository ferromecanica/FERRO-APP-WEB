"""Corregir el nombre de un proveedor, unir los repetidos y borrar los que sobran."""
from wsgi import app
from app.extensions import db
from app.models import ConfigMarkup, IngresoStock, PerfilLista, Proveedor, Repuesto
from app.services.stock import usos_del_proveedor
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))

with app.app_context():
    # Un proveedor cargado en mayúsculas y usado en los cuatro lados
    prov = Proveedor(nombre='PERNOS DEL SUR')
    db.session.add(prov)
    db.session.flush()
    pid = prov.id
    rep = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).first()
    rep.proveedor, rid = 'PERNOS DEL SUR', rep.id
    db.session.add(ConfigMarkup(proveedor='PERNOS DEL SUR', marca_envase=None, markup=1.4))
    db.session.add(IngresoStock(proveedor='PERNOS DEL SUR', estado='Borrador'))
    db.session.add(PerfilLista(proveedor='PERNOS DEL SUR', col_precio='PRECIO'))
    db.session.commit()
    assert sum(usos_del_proveedor('PERNOS DEL SUR').values()) == 4

# ── No se puede borrar uno que está en uso, y se explica por qué ──
b = post(f'/stock/proveedores/{pid}/eliminar')
assert 'No se puede borrar' in b and '1 repuestos' in b, b[b.find('No se puede'):b.find('No se puede') + 120]
with app.app_context():
    assert db.session.get(Proveedor, pid) is not None

# ── Corregir el nombre lo corrige en todos lados a la vez ──
b = post(f'/stock/proveedores/{pid}/editar', {'nombre': 'Pernos del Sur'})
assert '4 lugares' in b, b[b.find('ahora se llama'):b.find('ahora se llama') + 160]
with app.app_context():
    assert usos_del_proveedor('PERNOS DEL SUR') == dict.fromkeys(usos_del_proveedor('PERNOS DEL SUR'), 0), 'quedó algo con el nombre viejo'
    assert sum(usos_del_proveedor('Pernos del Sur').values()) == 4
    assert db.session.get(Proveedor, pid).nombre == 'Pernos del Sur'
    assert db.session.get(Repuesto, rid).proveedor == 'Pernos del Sur'

# ── El markup sigue valiendo: es lo que se rompería si el nombre quedara a medias ──
with app.app_context():
    from app.services.stock import regla_markup
    markup, origen = regla_markup(db.session.get(Repuesto, rid))
    assert markup == 1.4, (markup, origen)

# ── Cargado dos veces: renombrarlo al otro los une en uno solo ──
with app.app_context():
    repetido = Proveedor(nombre='PERNOS DEL SUR')       # lo vuelven a cargar en mayúsculas
    db.session.add(repetido)
    db.session.flush()
    otro_id = repetido.id
    suelto = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS, Repuesto.id != rid).first()
    suelto.proveedor, suelto_id = 'PERNOS DEL SUR', suelto.id
    db.session.commit()

b = post(f'/stock/proveedores/{otro_id}/editar', {'nombre': 'Pernos del Sur'})
assert 'cargado dos veces' in b, b[b.find('eran el mismo'):b.find('eran el mismo') + 160]
with app.app_context():
    assert db.session.get(Proveedor, otro_id) is None, 'el repetido tiene que desaparecer'
    assert db.session.get(Repuesto, suelto_id).proveedor == 'Pernos del Sur', 'su repuesto quedó apuntando a la nada'
    assert sum(usos_del_proveedor('Pernos del Sur').values()) == 5
    assert Proveedor.query.filter_by(nombre='Pernos del Sur').count() == 1

# ── Uno que no usa nadie se borra y listo ──
with app.app_context():
    libre = Proveedor(nombre='Nunca compramos acá')
    db.session.add(libre)
    db.session.commit()
    lid = libre.id
assert 'eliminado' in post(f'/stock/proveedores/{lid}/eliminar')
with app.app_context():
    assert db.session.get(Proveedor, lid) is None

# ── Un nombre vacío no borra el que estaba ──
assert 'Escribí el nombre' in post(f'/stock/proveedores/{pid}/editar', {'nombre': '   '})
with app.app_context():
    assert db.session.get(Proveedor, pid).nombre == 'Pernos del Sur'

# ── La pantalla los muestra con en qué se usan ──
b = B(c.get('/stock/markups'))
assert 'Proveedores' in b and 'Pernos del Sur' in b
assert 'id="proveedores"' in b

print('PROVEEDORES OK')
