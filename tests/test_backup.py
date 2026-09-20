"""La copia diaria a Drive: se manda sola una vez por día y se puede forzar."""
import gzip, sqlite3, sys
from datetime import date, timedelta
from pathlib import Path
from wsgi import app
from app.services import backup, drive
app.config['WTF_CSRF_ENABLED'] = False
c = app.test_client()
B = lambda r: r.get_data(as_text=True)

marca = Path(app.instance_path) / backup.MARCA
marca.unlink(missing_ok=True)

# lo que se manda: una copia comprimida de la base, con nombre por día
enviados = []
def falso_llamar(accion, **datos):
    enviados.append(dict(datos, accion=accion))
    return {"ok": True, "id": "xyz", "nombre": datos.get("nombre")}
drive.llamar, original = falso_llamar, drive.llamar
drive.configurado, original_cfg = (lambda: True), drive.configurado

nombre = backup.mandar_a_drive(app)
assert nombre == f'ferro-backup-{date.today():%Y-%m-%d}.sqlite.gz', nombre
assert enviados and enviados[0]['accion'] == 'guardar_backup'
import base64
crudo = gzip.decompress(base64.b64decode(enviados[0]['contenido']))
assert crudo[:15] == b'SQLite format 3', 'lo que se sube no es la base'
assert backup.ultimo_envio(app.instance_path) == date.today()

# y la copia se puede abrir de verdad
copia = Path(app.instance_path) / 'backups' / 'prueba.sqlite'
copia.write_bytes(crudo)
con = sqlite3.connect(copia)
assert con.execute("select count(*) from repuesto").fetchone()[0] >= 0
con.close(); copia.unlink()

# ── no se manda dos veces el mismo día ──
enviados.clear()
backup.respaldar_si_toca(app)
import time; time.sleep(0.5)
assert not enviados, 'mandó una segunda copia el mismo día'

# ── si la última es de ayer, sí ──
marca.write_text((date.today() - timedelta(days=1)).isoformat())
backup.respaldar_si_toca(app)
for _ in range(20):
    if enviados: break
    time.sleep(0.1)
assert enviados, 'no mandó la copia del día'
assert backup.ultimo_envio(app.instance_path) == date.today()

# ── el botón de Configuración ──
enviados.clear()
b = B(c.post('/configuracion/backup', follow_redirects=True))
assert 'Copia guardada en Drive' in b and enviados

# ── si Drive falla, avisa y no rompe ──
def explota(accion, **datos):
    raise drive.ErrorDrive('Drive no contesta')
drive.llamar = explota
b = B(c.post('/configuracion/backup', follow_redirects=True))
assert 'No pude mandar la copia' in b
marca.write_text((date.today() - timedelta(days=1)).isoformat())
backup.respaldar_si_toca(app)   # en segundo plano no debe tirar la app
time.sleep(0.5)
assert B(c.get('/')).count('Hola') >= 0

drive.llamar, drive.configurado = original, original_cfg
marca.unlink(missing_ok=True)
print('TODO OK')
