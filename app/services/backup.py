"""Copias de seguridad de la base SQLite."""
import sqlite3
from datetime import datetime
from pathlib import Path

COPIAS_LOCALES = 14


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
