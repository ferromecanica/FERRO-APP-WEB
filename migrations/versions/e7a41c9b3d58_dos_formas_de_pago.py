"""una venta se puede cobrar con dos formas de pago

Revision ID: e7a41c9b3d58
Revises: d5b2e94c1a77
Create Date: 2026-09-24 00:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7a41c9b3d58'
down_revision = 'd5b2e94c1a77'
branch_labels = None
depends_on = None


def upgrade():
    # Dónde cae la plata de cada forma de pago: el efectivo a la caja de Iván
    with op.batch_alter_table('condicion_pago', schema=None) as batch_op:
        batch_op.add_column(sa.Column('destino', sa.String(length=10), nullable=False,
                                      server_default='Banco'))
    op.execute("update condicion_pago set destino = 'Caja' where lower(nombre) = 'efectivo'")

    # Cada parte del cobro, con su comisión y su fecha de acreditación
    op.create_table(
        'pago_venta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('venta_id', sa.Integer(), nullable=False),
        sa.Column('condicion_id', sa.Integer(), nullable=True),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bruto', sa.Float(), nullable=False, server_default='0'),
        sa.Column('neto', sa.Float(), nullable=False, server_default='0'),
        sa.Column('fecha_acreditacion', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['condicion_id'], ['condicion_pago.id'], name='fk_pago_condicion'),
        sa.ForeignKeyConstraint(['venta_id'], ['venta.id'], name='fk_pago_venta'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('pago_venta', schema=None) as batch_op:
        batch_op.create_index('ix_pago_venta_venta_id', ['venta_id'])

    # Las ventas que ya están se quedan sin partes a propósito: su cobro sigue
    # leyéndose de bruto_cobrado / neto_acreditado, que es lo que se cargó en su
    # momento. Inventarles una parte sería decir que sabemos algo que no sabemos.


def downgrade():
    with op.batch_alter_table('pago_venta', schema=None) as batch_op:
        batch_op.drop_index('ix_pago_venta_venta_id')
    op.drop_table('pago_venta')
    with op.batch_alter_table('condicion_pago', schema=None) as batch_op:
        batch_op.drop_column('destino')
