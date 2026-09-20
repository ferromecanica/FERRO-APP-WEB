"""Deja la base como recién instalada: borra todos los datos cargados.

Uso:  python scripts/vaciar.py            (pide confirmación)
      python scripts/vaciar.py --si       (sin preguntar)

Conserva los usuarios (si no, nadie podría entrar) y la configuración del
taller. Todo lo demás —clientes, vehículos, OTs, ventas, turnos, repuestos,
presupuestos y movimientos— se borra. Hace una copia antes de tocar nada.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.services.backup import hacer_copia  # noqa: E402

CONSERVAR = {"usuario", "config_taller", "alembic_version"}


def vaciar():
    """Borra tabla por tabla, de las hijas a las padres (las claves foráneas mandan)."""
    borradas = {}
    for tabla in reversed(db.metadata.sorted_tables):
        if tabla.name in CONSERVAR:
            continue
        cuantas = db.session.execute(db.text(f"SELECT count(*) FROM {tabla.name}")).scalar()
        if cuantas:
            db.session.execute(tabla.delete())
            borradas[tabla.name] = cuantas
    db.session.commit()
    return borradas


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        if "--si" not in sys.argv:
            print(__doc__)
            if input('Escribí BORRAR para confirmar: ').strip() != "BORRAR":
                sys.exit("No se borró nada.")
        print("Copia de seguridad:", hacer_copia(app.config["SQLALCHEMY_DATABASE_URI"]).name)
        borradas = vaciar()
        if borradas:
            for tabla, cuantas in sorted(borradas.items(), key=lambda x: -x[1]):
                print(f"  − {cuantas:>6} {tabla}")
        print("✓ Base vacía. Quedaron los usuarios y la configuración del taller.")
