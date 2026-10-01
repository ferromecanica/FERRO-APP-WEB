"""la caja chica no replica en movimientos

Revision ID: c6a3f8d21b94
Revises: b5e2af7c1d43
Create Date: 2026-10-01 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6a3f8d21b94'
down_revision = 'b5e2af7c1d43'
branch_labels = None
depends_on = None


def upgrade():
    # El gasto del taller se carga a mano en Movimientos, porque pide comprobante,
    # CUIT, clasificación, neto e IVA. La caja solo dice cuánta plata hay en el
    # cajón, así que deja de apuntar a un egreso.
    #
    # Los egresos que ya se habían generado quedan donde están: son movimientos
    # como cualquier otro y se borran o se corrigen desde Movimientos.
    with op.batch_alter_table('movimiento_caja') as b:
        b.drop_column('movimiento_id')


def downgrade():
    with op.batch_alter_table('movimiento_caja') as b:
        b.add_column(sa.Column('movimiento_id', sa.Integer(), nullable=True))
        b.create_foreign_key('fk_movimiento_caja_movimiento', 'movimiento_contable',
                             ['movimiento_id'], ['id'])
