"""la caja chica de Iván

Revision ID: f2c76b8e4a19
Revises: e7a41c9b3d58
Create Date: 2026-09-24 23:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2c76b8e4a19'
down_revision = 'e7a41c9b3d58'
branch_labels = None
depends_on = None


def upgrade():
    # Cada parte del cobro se queda con el destino que tenía su forma de pago el
    # día que se cobró: cambiar la configuración no puede mudar plata que ya entró
    with op.batch_alter_table('pago_venta', schema=None) as batch_op:
        batch_op.add_column(sa.Column('destino', sa.String(length=10), nullable=False,
                                      server_default='Banco'))
    op.execute("""update pago_venta set destino = (
                      select destino from condicion_pago c where c.id = pago_venta.condicion_id)
                  where condicion_id is not null""")

    # Lo que sale de la caja: gastos de Iván, depósitos al banco, retiros y la apertura
    op.create_table(
        'movimiento_caja',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('monto', sa.Float(), nullable=False, server_default='0'),
        sa.Column('concepto', sa.String(length=300), nullable=True),
        sa.Column('quien', sa.String(length=120), nullable=True),
        sa.Column('movimiento_id', sa.Integer(), nullable=True),
        sa.Column('creado', sa.DateTime(), nullable=False),
        sa.Column('actualizado', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['movimiento_id'], ['movimiento_contable.id'], name='fk_caja_movimiento'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('movimiento_caja', schema=None) as batch_op:
        batch_op.create_index('ix_movimiento_caja_fecha', ['fecha'])


def downgrade():
    with op.batch_alter_table('movimiento_caja', schema=None) as batch_op:
        batch_op.drop_index('ix_movimiento_caja_fecha')
    op.drop_table('movimiento_caja')
    with op.batch_alter_table('pago_venta', schema=None) as batch_op:
        batch_op.drop_column('destino')
