"""La libretita de lo que hay que comprar: anotar, tildar y archivar."""
from datetime import date
from wsgi import app
from app.extensions import db
from app.models import AComprar, Repuesto
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))

with app.app_context():
    rep = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).order_by(Repuesto.id).first()
    rid, nombre = rep.id, rep.nombre
    assert AComprar.query.count() == 0, 'la libreta arranca vacía'

# ── Del stock: se engancha al repuesto, con o sin nota ──
post('/stock/comprar/nuevo', {'que': f'{rid} · {nombre}', 'nota': 'reponer, quedamos en cero'})
post('/stock/comprar/nuevo', {'que': str(rid)})                      # solo el código, como el escáner
with app.app_context():
    anotados = AComprar.query.order_by(AComprar.id).all()
    assert [a.repuesto_id for a in anotados] == [rid, rid], anotados
    assert anotados[0].nota == 'reponer, quedamos en cero'
    assert anotados[1].nota is None, 'la nota puede quedar en blanco'
    assert all(a.texto is None for a in anotados), 'si es del stock no se guarda texto libre'
    assert anotados[0].que_es == nombre

# ── A mano: lo que no está catalogado queda como texto ──
post('/stock/comprar/nuevo', {'que': 'Trapos y guantes', 'nota': 'en la ferretería'})
with app.app_context():
    a_mano = AComprar.query.filter_by(texto='Trapos y guantes').one()
    assert a_mano.repuesto_id is None and a_mano.que_es == 'Trapos y guantes'
    mid = a_mano.id

# ── Escribir el nombre exacto sin elegirlo de la lista igual lo cataloga ──
post('/stock/comprar/nuevo', {'que': nombre.lower()})
with app.app_context():
    assert AComprar.query.filter_by(repuesto_id=rid).count() == 3, 'no reconoció el nombre del repuesto'

# ── Sin escribir nada no se anota nada ──
antes = None
with app.app_context():
    antes = AComprar.query.count()
assert 'Escribí qué hay que comprar' in post('/stock/comprar/nuevo', {'que': '   '})
with app.app_context():
    assert AComprar.query.count() == antes, 'anotó una línea vacía'

# ── Tildar lo pasa a comprados con la fecha; destildar lo devuelve ──
post(f'/stock/comprar/{mid}/listo')
with app.app_context():
    a = db.session.get(AComprar, mid)
    assert a.comprado and a.fecha_comprado == date.today(), (a.comprado, a.fecha_comprado)
post(f'/stock/comprar/{mid}/listo')
with app.app_context():
    a = db.session.get(AComprar, mid)
    assert not a.comprado and a.fecha_comprado is None, 'destildar tiene que limpiar la fecha'
post(f'/stock/comprar/{mid}/listo')

# ── La pantalla: pendientes arriba, comprados abajo ──
b = B(c.get('/stock/comprar'))
assert 'A comprar' in b and 'Pendientes' in b
assert '3 pendientes' in b, b[b.find('Pendientes') - 200:b.find('Pendientes') + 200]
assert 'Ya comprados' in b and 'Trapos y guantes' in b
assert 'reponer, quedamos en cero' in b and 'en la ferretería' in b

# ── Borrar saca la anotación de la libreta ──
post(f'/stock/comprar/{mid}/eliminar')
with app.app_context():
    assert db.session.get(AComprar, mid) is None
    assert AComprar.query.filter_by(comprado=True).count() == 0

# ── Los archivados no tapan la pantalla: se ven los últimos ──
with app.app_context():
    from app.stock import TOPE_COMPRADOS
    for i in range(TOPE_COMPRADOS + 4):
        db.session.add(AComprar(texto=f'Comprado {i}', comprado=True, fecha_comprado=date.today()))
    db.session.commit()
b = B(c.get('/stock/comprar'))
assert f'{TOPE_COMPRADOS + 4} en total' in b
assert b.count('Comprado ') == TOPE_COMPRADOS, b.count('Comprado ')
assert f'Ver los {TOPE_COMPRADOS + 4}' in b
b = B(c.get('/stock/comprar?todos=1'))
assert b.count('Comprado ') == TOPE_COMPRADOS + 4, b.count('Comprado ')

print('A COMPRAR OK')
