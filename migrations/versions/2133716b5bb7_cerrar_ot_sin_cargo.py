"""cerrar ot sin cargo

Revision ID: 2133716b5bb7
Revises: f3b694ad7abb
Create Date: 2026-09-20 11:46:09.959142

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2133716b5bb7'
down_revision = 'f3b694ad7abb'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orden_trabajo', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sin_cargo', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('motivo_sin_cargo', sa.String(length=120), nullable=True))



def downgrade():
    with op.batch_alter_table('orden_trabajo', schema=None) as batch_op:
        batch_op.drop_column('motivo_sin_cargo')
        batch_op.drop_column('sin_cargo')

