import os
import time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# El servidor de PythonAnywhere corre en UTC: a partir de las 21 ya está en el
# día siguiente y las OT del día se irían a mañana. El taller está en Rosario,
# así que todo el proceso trabaja en hora argentina.
ZONA = os.environ.get("FERRO_TZ", "America/Argentina/Buenos_Aires")
os.environ["TZ"] = ZONA
if hasattr(time, "tzset"):
    time.tzset()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-no-usar-en-produccion")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'ferro.sqlite'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads"
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # las listas de precios de los proveedores son grandes
    MAX_FORM_MEMORY_SIZE = 16 * 1024 * 1024  # Werkzeug limita los campos de texto a 500 KB por defecto
    TALLER_NOMBRE = "Ferro"
    # Mientras no haya datos reales se entra sin login. Poner LOGIN_OBLIGATORIO=1 en .env para exigirlo.
    LOGIN_OBLIGATORIO = os.environ.get("LOGIN_OBLIGATORIO", "0") == "1"
