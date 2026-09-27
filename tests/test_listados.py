"""Ordenar y filtrar los listados: stock por columna, clientes y vehículos por ID."""
from wsgi import app
from app.extensions import db
from app.models import Cliente, Repuesto, Vehiculo
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)

with app.app_context():
    # Tres repuestos hechos para esta prueba, que se puedan distinguir entre sí
    ids = []
    for nombre, marca, stock in [('Filtro Fiat flojo', 'Fiat', 2),
                                 ('Filtro Chevrolet', 'Chevrolet', 40),
                                 ('Filtro Fiat surtido', 'Fiat', 7)]:
        r = Repuesto(nombre=nombre, comp_marca=marca, stock_actual=stock, descuento_oferta=0.20)
        db.session.add(r)
        db.session.flush()
        ids.append(r.id)
    db.session.commit()
    cuantos = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).count()

cuerpo = lambda url: B(c.get(url)).split('<tbody>')[1]

# ── Filtrar por una columna: solo los Fiat ──
b = cuerpo('/stock/?f_comp_marca=fiat')
assert 'Filtro Fiat flojo' in b and 'Filtro Fiat surtido' in b
assert 'Filtro Chevrolet' not in b, 'se coló un Chevrolet filtrando por Fiat'

# ── Mayúsculas y acentos no importan ──
assert cuerpo('/stock/?f_comp_marca=FIAT') == b

# ── Los números aceptan comparaciones, y se combinan con las otras columnas ──
b = cuerpo('/stock/?f_comp_marca=fiat&f_stock=>5')
assert 'Filtro Fiat surtido' in b and 'Filtro Fiat flojo' not in b, 'el > no filtró por stock'
assert 'Filtro Chevrolet' not in b, 'el filtro de marca se perdió al agregar el de stock'
b = cuerpo('/stock/?f_stock=<=2')
assert 'Filtro Fiat flojo' in b and 'Filtro Chevrolet' not in b

# ── El descuento se escribe en % aunque se guarde como fracción ──
assert 'Filtro Fiat flojo' in cuerpo('/stock/?f_descuento=20')
assert 'No hay repuestos' in B(c.get('/stock/?f_descuento=0,20')), 'el % se interpretó como fracción' 

# ── Lo que no se entiende no devuelve cualquier cosa: devuelve nada ──
assert 'No hay repuestos' in B(c.get('/stock/?f_stock=ocho'))

# ── Sin filtros se ven todos: ya no hay tope de filas ──
b = B(c.get('/stock/'))
assert f'{cuantos} repuestos' in b, 'el listado dejó de mostrar todo'
assert 'Ver todas' not in b and 'Mostrando las primeras' not in b

# ── Clientes: el ID va en su propia columna y ordena por él ──
with app.app_context():
    primero = Cliente.query.order_by(Cliente.id).first()
    ultimo = Cliente.query.order_by(Cliente.id.desc()).first()
b = B(c.get('/clientes/'))
assert primero.codigo in b and b.index(primero.codigo) < b.index(ultimo.codigo), 'no arranca ordenado por ID'
b = B(c.get('/clientes/?orden=id&dir=desc'))
assert b.index(ultimo.codigo) < b.index(primero.codigo), 'no ordenó al revés'

# Ordenar por nombre no es lo mismo que ordenar por ID
porid = B(c.get('/clientes/?orden=id&dir=asc'))
pornombre = B(c.get('/clientes/?orden=cliente&dir=desc'))
assert porid != pornombre

# ── Vehículos: su propio código, y ordena por lo que se toque ──
with app.app_context():
    v = Vehiculo.query.order_by(Vehiculo.id).first()
    assert v.codigo == f'VEH-{v.id:03d}', v.codigo
b = B(c.get('/clientes/vehiculos'))
assert v.codigo in b
b = B(c.get('/clientes/vehiculos?orden=km&dir=desc'))
assert 'ordenada' in b, 'no marcó la columna por la que está ordenando'

# ── Una columna que no existe no rompe nada ──
assert c.get('/clientes/?orden=loquesea').status_code == 200
assert c.get('/stock/?f_inventado=x').status_code == 200

print('LISTADOS OK')
