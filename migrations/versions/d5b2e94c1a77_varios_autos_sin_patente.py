"""puede haber varios autos SIN PATENTE

Revision ID: d5b2e94c1a77
Revises: c3f81a5d7e02
Create Date: 2026-09-23 02:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5b2e94c1a77'
down_revision = 'c3f81a5d7e02'
branch_labels = None
depends_on = None

SIN_PATENTE = "SINPATENTE"


def upgrade():
    # El índice único tapaba al segundo auto sin chapa, aunque el formulario ya
    # los dejaba pasar: ahora la unicidad vale para las patentes de verdad
    op.drop_index('ix_vehiculo_patente', table_name='vehiculo')
    op.create_index('ix_vehiculo_patente', 'vehiculo', ['patente'], unique=True,
                    sqlite_where=sa.text(f"patente <> '{SIN_PATENTE}'"))


def downgrade():
    # Vuelve a haber un solo lugar para los autos sin chapa
    op.drop_index('ix_vehiculo_patente', table_name='vehiculo')
    op.create_index('ix_vehiculo_patente', 'vehiculo', ['patente'], unique=True)
