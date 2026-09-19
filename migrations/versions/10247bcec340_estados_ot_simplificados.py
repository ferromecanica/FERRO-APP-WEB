"""estados ot simplificados

Revision ID: 10247bcec340
Revises: d525b7ffd07d
Create Date: 2026-09-18 23:01:59.034084

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '10247bcec340'
down_revision = 'd525b7ffd07d'
branch_labels = None
depends_on = None


# Estados viejos -> nuevos (Pendiente | En proceso | Finalizada)
MAPEO = {
    "Ingresado": "Pendiente",
    "En diagnóstico": "En proceso",
    "Esperando repuestos": "En proceso",
    "En reparación": "En proceso",
    "Terminado": "Finalizada",
    "Entregado": "Finalizada",
}


def upgrade():
    tabla = sa.table("orden_trabajo", sa.column("estado", sa.String))
    for viejo, nuevo in MAPEO.items():
        op.execute(tabla.update().where(tabla.c.estado == viejo).values(estado=nuevo))


def downgrade():
    tabla = sa.table("orden_trabajo", sa.column("estado", sa.String))
    op.execute(tabla.update().where(tabla.c.estado == "Pendiente").values(estado="Ingresado"))
    op.execute(tabla.update().where(tabla.c.estado == "En proceso").values(estado="En reparación"))
    op.execute(tabla.update().where(tabla.c.estado == "Finalizada").values(estado="Terminado"))
