"""archivar presupuestos

Revision ID: 1b7f66199561
Revises: 005881a5e72d
Create Date: 2026-09-19 20:45:16.418715

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '1b7f66199561'
down_revision = '005881a5e72d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('presupuesto', schema=None) as batch_op:
        batch_op.add_column(sa.Column('archivado', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('presupuesto', schema=None) as batch_op:
        batch_op.drop_column('archivado')
