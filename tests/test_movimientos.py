"""Historia de cada repuesto (dónde se usó) y auditoría de ajustes de inventario."""
import re
from wsgi import app
from app.extensions import db
from app.models import CondicionPago, MovimientoStock, OrdenTrabajo, Repuesto
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None): return B(c.post(url, data=d or {}, follow_redirects=True))
# Las formas de pago ahora son filas de CondicionPago (traen la comisión de la tarjeta)
def condicion(nombre):
    with app.app_context():
        return str(CondicionPago.query.filter_by(nombre=nombre).one().id)

def limpio(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))

with app.app_context():
    r = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).first()
    r.stock_actual = 10
    db.session.commit()
    rid, rnombre, rstock = r.id, r.nombre, r.stock_actual
    ot = OrdenTrabajo.query.filter(OrdenTrabajo.estado != 'Finalizada').first()
    otid, patente = ot.id, ot.vehiculo.patente

# ── se usa en una OT y en una venta de mostrador ──
post(f'/ot/{otid}/repuestos', {'repuesto': str(rid), 'cantidad': '2'})
post('/ventas/mostrador/items', {'tipo': 'stock', 'repuesto': str(rid), 'cantidad': '1'})
post('/ventas/mostrador/cobrar', {'pago_condicion_1': condicion('Efectivo')})

b = limpio(B(c.get(f'/stock/{rid}')))
historia = b[b.find('Dónde se usó'):b.find('Movimientos de stock')]
assert '2 veces' in historia and '3 unidades' in historia, historia[:200]
assert f'OT #{otid}' in historia and patente in historia, 'falta la OT donde se usó'
assert 'mostrador' in historia, 'falta la venta de mostrador'

# ── ajuste de inventario: queda quién, cuándo y de cuánto a cuánto ──
b = post(f'/stock/{rid}/ajuste', {'stock_nuevo': '5', 'motivo': 'conteo de fin de mes'})
assert 'Stock ajustado a 5' in b
with app.app_context():
    m = MovimientoStock.query.filter_by(repuesto_id=rid, tipo='Ajuste').order_by(MovimientoStock.id.desc()).first()
    assert m.detalle == 'conteo de fin de mes'
    assert m.stock_resultante == 5 and m.stock_anterior == rstock - 3
    assert m.usuario is not None, 'no guardó quién lo hizo'
    quien = m.usuario.nombre

b = limpio(B(c.get('/stock/movimientos')))
assert 'conteo de fin de mes' in b and rnombre[:20] in b and quien in b
assert '7 → 5' in b.replace(' ', ' '), b[b.find('conteo'):][:200]
# por defecto solo ajustes: el consumo de la OT no aparece
assert 'Consumo' not in b.split('Ajustes de inventario')[-1]
# y en "todo el libro" sí
todo = limpio(B(c.get('/stock/movimientos?tipo=')))
assert 'Consumo' in todo and 'Venta' in todo
# búsqueda
assert 'conteo de fin de mes' in limpio(B(c.get('/stock/movimientos?q=conteo')))
assert 'conteo de fin de mes' not in limpio(B(c.get('/stock/movimientos?q=zzzz')))
print('TODO OK')
