"""Listas de precios: leer el archivo del proveedor, mapear columnas y aplicar."""
import io
import re
from wsgi import app
from app.extensions import db
from app.models import PerfilLista, Repuesto
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)
def post(url, d=None, **kw): return B(c.post(url, data=d or {}, follow_redirects=True, **kw))

# repuestos propios de esta prueba, para no depender de lo que haya en la base
with app.app_context():
    datos = []
    for i, (parte, marca, costo) in enumerate([('AP-1001', 'MAHLE', 10000.0), ('AP 1002', 'SKF', 25500.5),
                                               ('AP-1003', 'SACHS', 1200.0)]):
        r = Repuesto.query.filter_by(nro_parte=parte).first() or Repuesto(nro_parte=parte)
        r.nombre, r.marca, r.proveedor, r.costo_lista = f'Repuesto de prueba {i + 1}', marca, 'RSF', costo
        db.session.add(r)
        db.session.flush()
        datos.append((r.id, parte, marca, costo))
    db.session.commit()

# el proveedor manda un CSV con el precio de venta: el costo es el 57,11 %
archivo = 'ARTICULO;MARCA;DESCRIPCION;PRECIOVTA\n' + '\n'.join(
    f'{parte};{marca};lo que sea;{costo * 2:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    for _, parte, marca, costo in datos) + '\nZZZ999;OTRA;no la tenemos;1.000,00\n'
b = post('/stock/listas', {'proveedor': 'RSF', 'archivo': (io.BytesIO(archivo.encode()), 'lista.csv')},
         content_type='multipart/form-data')
assert 'ARTICULO' in b and 'PRECIOVTA' in b, b[:600]

# sin decirle qué columna es cuál no calcula nada
assert 'qué columna trae el código' in post('/stock/listas/revisar', {'col_codigo': '', 'col_precio': ''})

mapeo = {'col_codigo': 'ARTICULO', 'col_marca': 'MARCA', 'col_precio': 'PRECIOVTA',
         'campo_codigo': 'nro_parte', 'factor': '0,5711'}
b = post('/stock/listas/revisar', mapeo)
assert f'{len(datos)} cambian' in b, b[b.find('Qué cambiaría'):][:400]
assert '1 filas del archivo que no tenemos' in b

# aplicar
b = post('/stock/listas/revisar', dict(mapeo, accion='aplicar'))
assert f'{len(datos)} precios actualizados de RSF' in b
with app.app_context():
    for rid, _, _, viejo in datos:
        r = db.session.get(Repuesto, rid)
        esperado = round(viejo * 2 * 0.5711, 2)
        assert abs(r.costo_lista - esperado) < 0.02, (rid, r.costo_lista, esperado)
        from app.services.stock import markup_para
        assert abs(r.precio_venta - round(r.precio_costo * markup_para(r), 2)) < 0.02, (rid, r.precio_venta)
    perfil = PerfilLista.query.filter_by(proveedor='RSF').one()
    assert (perfil.col_codigo, perfil.col_precio, round(perfil.factor, 4)) == ('ARTICULO', 'PRECIOVTA', 0.5711)
    assert perfil.actualizada is not None

# el mapeo queda puesto la próxima vez
b = post('/stock/listas', {'proveedor': 'RSF', 'archivo': (io.BytesIO(archivo.encode()), 'lista.csv')},
         content_type='multipart/form-data')
assert re.search(r'<option value="ARTICULO" selected', b), 'no recordó el mapeo'
assert 'quedan igual' in b and '0 cambian' in b.replace('\n', ' ')


# envase: el precio del archivo es por bidón y el de 16 rinde 4
with app.app_context():
    r = Repuesto.query.filter_by(proveedor='Shell').first()
    r.nro_parte = 'L73351'; db.session.commit(); rid = r.id
archivo2 = 'Codigo,Pcio. Final,Env.\nL73351,"64.000,00",16\n'
post('/stock/listas', {'proveedor': 'Shell', 'archivo': (io.BytesIO(archivo2.encode()), 'fgc.csv')},
     content_type='multipart/form-data')
b = post('/stock/listas/revisar', {'col_codigo': 'Codigo', 'col_precio': 'Pcio. Final', 'col_envase': 'Env.',
                                   'campo_codigo': 'nro_parte', 'factor': '0,88', 'equivalencias': '16=4'})
assert '1 cambian' in b
b = post('/stock/listas/revisar', {'col_codigo': 'Codigo', 'col_precio': 'Pcio. Final', 'col_envase': 'Env.',
                                   'campo_codigo': 'nro_parte', 'factor': '0,88', 'equivalencias': '16=4',
                                   'accion': 'aplicar'})
assert '1 precios actualizados de Shell' in b
with app.app_context():
    assert db.session.get(Repuesto, rid).costo_lista == round(64000 / 4 * 0.88, 2)

# control: si el archivo viene con otra forma, no toca nada
with app.app_context():
    r0 = Repuesto.query.filter_by(proveedor='RSF').filter(Repuesto.costo_lista > 0).first()
    rid0, costo0 = r0.id, r0.costo_lista
recortado = 'ARTICULO;MARCA;PRECIOVTA\n' + f'{datos[0][1]};{datos[0][2]};1.000,00\n'
post('/stock/listas', {'proveedor': 'RSF', 'archivo': (io.BytesIO(recortado.encode()), 'lista.csv')},
     content_type='multipart/form-data')
b = post('/stock/listas/revisar', {'col_codigo': 'ARTICULO', 'col_marca': 'MARCA', 'col_precio': 'PRECIOVTA',
                                   'campo_codigo': 'nro_parte', 'factor': '0,5711', 'accion': 'aplicar'})
assert 'no vino como se esperaba' in b, b[:800]
assert '3 columnas' in b and 'siempre trae 4' in b
assert 'Aplicar los' not in b, 'no tendría que dejar aplicar'
with app.app_context():
    assert db.session.get(Repuesto, rid0).costo_lista == costo0, 'tocó un precio con el archivo mal'
post('/stock/listas/cancelar')

# archivo sin fila de títulos (como el TXT de RSF): las columnas se llaman "Columna N"
with app.app_context():
    r = Repuesto(nombre='Repuesto de prueba 4', nro_parte='AP-2001', marca='FRAM',
                 proveedor='Gatti', costo_lista=500.0)
    db.session.add(r); db.session.commit()
    rid, parte, marca = r.id, r.nro_parte, r.marca
sin_titulos = f'"{marca}","{parte}","RUBRO","lo que sea",1234.50,0.00,"","R01",""\n"OTRA","ZZZ","X","y",99.00,0.00,"","R02",""\n'
b = post('/stock/listas', {'proveedor': 'Gatti', 'archivo': (io.BytesIO(sin_titulos.encode()), 'lista.TXT')},
         content_type='multipart/form-data')
assert 'Columna 5' in b and 'RUBRO' in b, 'no tomó las columnas genéricas'
b = post('/stock/listas/revisar', {'col_codigo': 'Columna 2', 'col_marca': 'Columna 1', 'col_precio': 'Columna 5',
                                   'campo_codigo': 'nro_parte', 'factor': '0,5711', 'accion': 'aplicar'})
assert '1 precios actualizados' in b
with app.app_context():
    assert db.session.get(Repuesto, rid).costo_lista == round(1234.50 * 0.5711, 2)

# archivo que no se puede leer
assert 'No pude' in post('/stock/listas', {'proveedor': 'RSF', 'archivo': (io.BytesIO(b'%PDF-1.4 roto'), 'lista.pdf')},
                          content_type='multipart/form-data')
assert 'tiene que ser Excel' in post('/stock/listas', {'proveedor': 'RSF', 'archivo': (io.BytesIO(b'x'), 'lista.docx')},
                                     content_type='multipart/form-data')
print('TODO OK')
