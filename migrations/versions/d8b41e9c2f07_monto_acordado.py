"""cuánto nos tienen que pagar

Revision ID: d8b41e9c2f07
Revises: c6a3f8d21b94
Create Date: 2026-10-07 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8b41e9c2f07'
down_revision = 'c6a3f8d21b94'
branch_labels = None
depends_on = None


def upgrade():
    # Lo acordado con el cliente al cerrar una OT que queda por cobrar. Las que
    # ya están cerradas quedan en vacío: ahí no hay nada que recordar.
    with op.batch_alter_table('orden_trabajo') as b:
        b.add_column(sa.Column('monto_acordado', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('orden_trabajo') as b:
        b.drop_column('monto_acordado')
