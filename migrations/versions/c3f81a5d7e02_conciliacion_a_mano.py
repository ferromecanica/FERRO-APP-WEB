"""conciliación a mano: ventas revisadas e ingresos emparejados

Revision ID: c3f81a5d7e02
Revises: a5a932514562
Create Date: 2026-09-22 21:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f81a5d7e02'
down_revision = 'a5a932514562'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('venta', schema=None) as batch_op:
        batch_op.add_column(sa.Column('revisada', sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table('movimiento_contable', schema=None) as batch_op:
        batch_op.add_column(sa.Column('venta_conciliada_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_movimiento_venta_conciliada', 'venta', ['venta_conciliada_id'], ['id'])


def downgrade():
    with op.batch_alter_table('movimiento_contable', schema=None) as batch_op:
        batch_op.drop_constraint('fk_movimiento_venta_conciliada', type_='foreignkey')
        batch_op.drop_column('venta_conciliada_id')

    with op.batch_alter_table('venta', schema=None) as batch_op:
        batch_op.drop_column('revisada')
