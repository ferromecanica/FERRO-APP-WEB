"""Comunicación con el Apps Script de Google (docs/reportes_gdrive.gs).

Un solo punto de contacto para todo lo que vive en Drive: reportes PDF y fotos.
"""
import json
import os
import urllib.parse
import urllib.request


class ErrorDrive(Exception):
    pass


def configurado():
    return bool(os.environ.get("REPORTES_URL") and os.environ.get("BACKUP_SECRET"))


def llamar(accion, **datos):
    """Llama al Apps Script con una acción y devuelve su respuesta (dict con ok=True)."""
    if not configurado():
        raise ErrorDrive("Falta configurar la conexión con Google Drive (REPORTES_URL en el servidor).")
    cuerpo = urllib.parse.urlencode({"secreto": os.environ["BACKUP_SECRET"], "accion": accion, **datos}).encode()
    try:
        with urllib.request.urlopen(os.environ["REPORTES_URL"], data=cuerpo, timeout=120) as r:
            respuesta = r.read().decode()
    except OSError as e:
        raise ErrorDrive(f"No pude comunicarme con Google Drive ({e}).")
    try:
        resultado = json.loads(respuesta)
    except ValueError:
        raise ErrorDrive("Google Drive respondió algo inesperado.")
    if not resultado.get("ok"):
        raise ErrorDrive(f"Google Drive rechazó el pedido: {resultado.get('error', 'error desconocido')}.")
    return resultado
