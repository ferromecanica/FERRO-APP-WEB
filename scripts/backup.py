"""Copia manual de la base en instance/backups/ (la diaria la dispara Google Apps Script).

Uso en PythonAnywhere:  ~/.venvs/ferro/bin/python ~/FERRO/scripts/backup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.backup import hacer_copia  # noqa: E402
from config import Config  # noqa: E402

if __name__ == "__main__":
    copia = hacer_copia(Config.SQLALCHEMY_DATABASE_URI)
    print(f"✓ Copia: {copia} ({copia.stat().st_size / 1024:.0f} KB)")
