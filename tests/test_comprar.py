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

# ── La cantidad: se anota cuántos faltan y se compra de a partes ──
post('/stock/comprar/nuevo', {'que': 'Bujías NGK', 'cantidad': '4'})
with app.app_context():
    bujias = AComprar.query.filter_by(texto='Bujías NGK').one()
    assert bujias.cantidad == 4, bujias.cantidad
    bid = bujias.id

# El proveedor solo tenía 2: se archivan esas y quedan 2 pendientes
post(f'/stock/comprar/{bid}/listo', {'cantidad': '2'})
with app.app_context():
    quedan = db.session.get(AComprar, bid)
    assert quedan.cantidad == 2 and not quedan.comprado, (quedan.cantidad, quedan.comprado)
    compradas = AComprar.query.filter_by(texto='Bujías NGK', comprado=True).one()
    assert compradas.cantidad == 2 and compradas.fecha_comprado == date.today()

# Las 2 que faltaban, completas: la línea se cierra entera
post(f'/stock/comprar/{bid}/listo', {'cantidad': '2'})
with app.app_context():
    assert db.session.get(AComprar, bid).comprado, 'no cerró la línea al comprar todo'

# Si compró de más, queda lo que realmente trajo
post('/stock/comprar/nuevo', {'que': 'Trapos rejilla', 'cantidad': '3'})
with app.app_context():
    tid = AComprar.query.filter_by(texto='Trapos rejilla').one().id
post(f'/stock/comprar/{tid}/listo', {'cantidad': '5'})
with app.app_context():
    t5 = db.session.get(AComprar, tid)
    assert t5.comprado and t5.cantidad == 5, (t5.comprado, t5.cantidad)

# Sin decir cuántos, se da por comprado todo lo anotado
post('/stock/comprar/nuevo', {'que': 'Silicona', 'cantidad': '2'})
with app.app_context():
    sid = AComprar.query.filter_by(texto='Silicona').one().id
post(f'/stock/comprar/{sid}/listo')
with app.app_context():
    s = db.session.get(AComprar, sid)
    assert s.comprado and s.cantidad == 2, (s.comprado, s.cantidad)

# Cero no es una compra
with app.app_context():
    antes_cero = AComprar.query.filter_by(comprado=True).count()
post('/stock/comprar/nuevo', {'que': 'Fusibles', 'cantidad': '2'})
with app.app_context():
    fid = AComprar.query.filter_by(texto='Fusibles').one().id
assert 'más de cero' in post(f'/stock/comprar/{fid}/listo', {'cantidad': '0'})
with app.app_context():
    assert not db.session.get(AComprar, fid).comprado
    assert AComprar.query.filter_by(comprado=True).count() == antes_cero
    db.session.delete(db.session.get(AComprar, fid))
    db.session.commit()

# Anotar una cantidad inválida no anota nada
with app.app_context():
    antes = AComprar.query.count()
assert 'mayor a cero' in post('/stock/comprar/nuevo', {'que': 'Algo', 'cantidad': '0'})
with app.app_context():
    assert AComprar.query.count() == antes

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
    assert AComprar.query.filter_by(texto='Trapos y guantes').count() == 0

# ── Los archivados no tapan la pantalla: se ven los últimos ──
with app.app_context():
    from app.stock import TOPE_COMPRADOS
    for i in range(TOPE_COMPRADOS + 4):
        db.session.add(AComprar(texto=f'Comprado {i}', comprado=True, fecha_comprado=date.today()))
    db.session.commit()
    archivados = AComprar.query.filter_by(comprado=True).count()
b = B(c.get('/stock/comprar'))
assert f'{archivados} en total' in b
assert b.count('Comprado ') == TOPE_COMPRADOS, b.count('Comprado ')
assert f'Ver los {archivados}' in b
b = B(c.get('/stock/comprar?todos=1'))
assert b.count('Comprado ') == TOPE_COMPRADOS + 4, b.count('Comprado ')

print('A COMPRAR OK')
