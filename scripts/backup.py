"""Copia de seguridad de la base: copia local con fecha + copia en Google Drive.

Corre en PythonAnywhere como tarea programada diaria:
    ~/.venvs/ferro/bin/python ~/FERRO/scripts/backup.py

- Hace una copia consistente con la API de backup de SQLite (sirve aunque la
  app esté escribiendo en ese momento).
- Guarda las últimas COPIAS_LOCALES en instance/backups/.
- Si en .env están BACKUP_GDRIVE_URL y BACKUP_SECRET, sube la copia
  comprimida al Apps Script de docs/backup_gdrive.gs, que la guarda en Drive.
"""
import base64
import gzip
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from config import Config  # noqa: E402  (carga .env)

COPIAS_LOCALES = 14


def ruta_base():
    uri = Config.SQLALCHEMY_DATABASE_URI
    if not uri.startswith("sqlite:///"):
        sys.exit(f"Solo sé respaldar SQLite, la base es {uri.split(':')[0]}")
    return Path(uri.replace("sqlite:///", "", 1))


def copia_local(origen):
    carpeta = origen.parent / "backups"
    carpeta.mkdir(exist_ok=True)
    destino = carpeta / f"ferro-{datetime.now():%Y-%m-%d_%H%M}.sqlite"
    fuente, copia = sqlite3.connect(origen), sqlite3.connect(destino)
    try:
        fuente.backup(copia)
    finally:
        fuente.close()
        copia.close()
    for vieja in sorted(carpeta.glob("ferro-*.sqlite"))[:-COPIAS_LOCALES]:
        vieja.unlink()
    return destino


def subir_a_drive(archivo):
    url, secreto = os.environ.get("BACKUP_GDRIVE_URL"), os.environ.get("BACKUP_SECRET")
    if not (url and secreto):
        print("· Google Drive no configurado (faltan BACKUP_GDRIVE_URL / BACKUP_SECRET en .env)")
        return
    datos = urllib.parse.urlencode({
        "secreto": secreto,
        "nombre": archivo.name + ".gz",
        "contenido": base64.b64encode(gzip.compress(archivo.read_bytes())).decode(),
    }).encode()
    with urllib.request.urlopen(url, data=datos, timeout=120) as r:
        respuesta = r.read().decode()
    try:
        resultado = json.loads(respuesta)
    except ValueError:
        sys.exit(f"✗ Drive respondió algo inesperado: {respuesta[:200]}")
    if not resultado.get("ok"):
        sys.exit(f"✗ Drive rechazó la copia: {resultado.get('error')}")
    print(f"✓ Subida a Google Drive: {resultado.get('archivo')}")


if __name__ == "__main__":
    copia = copia_local(ruta_base())
    print(f"✓ Copia local: {copia} ({copia.stat().st_size / 1024:.0f} KB)")
    subir_a_drive(copia)
