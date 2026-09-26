"""la libretita de lo que hay que comprar

Revision ID: a4d19e6b3c25
Revises: f2c76b8e4a19
Create Date: 2026-09-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4d19e6b3c25'
down_revision = 'f2c76b8e4a19'
branch_labels = None
depends_on = None


def upgrade():
    # Un pendiente es un repuesto del stock o un texto escrito a mano: de ahí que
    # las dos columnas puedan estar vacías, pero nunca las dos a la vez.
    op.create_table(
        'a_comprar',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repuesto_id', sa.Integer(), nullable=True),
        sa.Column('texto', sa.String(length=200), nullable=True),
        sa.Column('nota', sa.String(length=300), nullable=True),
        sa.Column('comprado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('fecha_comprado', sa.Date(), nullable=True),
        sa.Column('anotado_por', sa.String(length=120), nullable=True),
        sa.Column('creado', sa.DateTime(), nullable=False),
        sa.Column('actualizado', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['repuesto_id'], ['repuesto.id'], name='fk_a_comprar_repuesto'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('a_comprar') as b:
        b.create_index('ix_a_comprar_comprado', ['comprado'])


def downgrade():
    with op.batch_alter_table('a_comprar') as b:
        b.drop_index('ix_a_comprar_comprado')
    op.drop_table('a_comprar')
