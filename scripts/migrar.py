"""Deja la base al día con las migraciones (lo corre el deploy en el servidor).

Si la base fue creada antes de usar migraciones (tiene tablas pero no la
tabla alembic_version), primero la marca como "esquema inicial".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from flask_migrate import stamp, upgrade  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db, migrate  # noqa: E402
from app.services.backup import hacer_copia  # noqa: E402

ESQUEMA_INICIAL = "a1749331c4e6"

app = create_app()
with app.app_context():
    tablas = inspect(db.engine).get_table_names()
    if tablas and "alembic_version" not in tablas:
        print("Base previa a las migraciones: la marco como esquema inicial.")
        stamp(revision=ESQUEMA_INICIAL)
    with db.engine.connect() as conexion:
        actual = MigrationContext.configure(conexion).get_current_revision()
    ultima = ScriptDirectory.from_config(migrate.get_config()).get_current_head()
    if actual != ultima:
        if tablas:
            copia = hacer_copia(app.config["SQLALCHEMY_DATABASE_URI"])
            print(f"Copia antes de migrar: {copia.name}")
        upgrade()
        print(f"✓ Base actualizada ({actual} → {ultima})")
    else:
        print("✓ Base al día")
