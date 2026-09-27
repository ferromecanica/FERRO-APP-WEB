"""cuántos hay que comprar

Revision ID: b5e2af7c1d43
Revises: a4d19e6b3c25
Create Date: 2026-09-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5e2af7c1d43'
down_revision = 'a4d19e6b3c25'
branch_labels = None
depends_on = None


def upgrade():
    # Lo anotado hasta ahora era de a uno: ese es el valor con el que arrancan
    with op.batch_alter_table('a_comprar') as b:
        b.add_column(sa.Column('cantidad', sa.Float(), nullable=False, server_default='1'))


def downgrade():
    with op.batch_alter_table('a_comprar') as b:
        b.drop_column('cantidad')
