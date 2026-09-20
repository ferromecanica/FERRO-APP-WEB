"""Copias de seguridad de la base SQLite.

Hay dos: la local (instance/backups/, sirve para volver atrás en el momento) y
la de Google Drive, que es la que vale si el servidor se pierde. La de Drive la
manda Ferro mismo una vez por día, en la primera visita de la jornada: en el
PythonAnywhere gratis no hay tareas programadas.
"""
import base64
import gzip
import sqlite3
import threading
import traceback
from datetime import date, datetime
from pathlib import Path

COPIAS_LOCALES = 14
MARCA = "ultimo-backup.txt"  # la fecha del último envío a Drive
_candado = threading.Lock()


def ruta_base(uri):
    if not uri.startswith("sqlite:///"):
        raise ValueError(f"Solo sé respaldar SQLite, la base es {uri.split(':')[0]}")
    return Path(uri.replace("sqlite:///", "", 1))


def hacer_copia(uri):
    """Copia consistente (aunque la app esté escribiendo) en instance/backups/.

    Conserva las últimas COPIAS_LOCALES y devuelve la ruta de la nueva.
    """
    origen = ruta_base(uri)
    carpeta = origen.parent / "backups"
    carpeta.mkdir(exist_ok=True)
    destino = carpeta / f"ferro-{datetime.now():%Y-%m-%d_%H%M%S}.sqlite"
    fuente, copia = sqlite3.connect(origen), sqlite3.connect(destino)
    try:
        fuente.backup(copia)
    finally:
        fuente.close()
        copia.close()
    for vieja in sorted(carpeta.glob("ferro-*.sqlite"))[:-COPIAS_LOCALES]:
        vieja.unlink()
    return destino


# ─────────────────────────── La copia que va a Drive ────────────────────────


def _marca(instance_path):
    return Path(instance_path) / MARCA


def ultimo_envio(instance_path):
    """Fecha del último backup mandado a Drive, o None si nunca se mandó."""
    try:
        return datetime.strptime(_marca(instance_path).read_text().strip()[:10], "%Y-%m-%d").date()
    except (OSError, ValueError):
        return None


def mandar_a_drive(app):
    """Hace una copia y la sube a la carpeta de backups de Drive. Devuelve el nombre."""
    from . import drive

    copia = hacer_copia(app.config["SQLALCHEMY_DATABASE_URI"])
    nombre = f"ferro-backup-{date.today():%Y-%m-%d}.sqlite.gz"
    contenido = base64.b64encode(gzip.compress(copia.read_bytes())).decode()
    drive.llamar("guardar_backup", nombre=nombre, contenido=contenido)
    _marca(app.instance_path).write_text(date.today().isoformat())
    return nombre


def respaldar_si_toca(app):
    """Si hoy todavía no se mandó copia a Drive, la manda en segundo plano."""
    from . import drive

    if not drive.configurado() or ultimo_envio(app.instance_path) == date.today():
        return
    if not _candado.acquire(blocking=False):
        return  # ya hay una copia en curso

    def trabajo():
        try:
            with app.app_context():
                if ultimo_envio(app.instance_path) != date.today():
                    app.logger.info("Backup diario en Drive: %s", mandar_a_drive(app))
        except Exception:
            app.logger.warning("No pude mandar el backup a Drive:\n%s", traceback.format_exc())
        finally:
            _candado.release()

    threading.Thread(target=trabajo, daemon=True).start()
