import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-no-usar-en-produccion")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'ferro.sqlite'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    TALLER_NOMBRE = "Ferro"
