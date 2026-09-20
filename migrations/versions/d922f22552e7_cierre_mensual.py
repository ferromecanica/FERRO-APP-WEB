"""cierre mensual

Revision ID: d922f22552e7
Revises: b8dae7241cc3
Create Date: 2026-09-20 13:14:26.769903

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd922f22552e7'
down_revision = 'b8dae7241cc3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cierre_socio',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cierre_id', sa.Integer(), nullable=False),
    sa.Column('socio_id', sa.Integer(), nullable=False),
    sa.Column('sueldo', sa.Float(), nullable=True),
    sa.Column('repago', sa.Float(), nullable=True),
    sa.Column('ganancia', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['cierre_id'], ['cierre_mensual.id'], ),
    sa.ForeignKeyConstraint(['socio_id'], ['socio.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('aporte_capital', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cierre_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_cierre', 'cierre_mensual', ['cierre_id'], ['id'])

    with op.batch_alter_table('cierre_mensual', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ingresos', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('egresos', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('colchon_entrante', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('repago', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('ganancia', sa.Float(), nullable=True))
        batch_op.alter_column('modo',
               existing_type=sa.VARCHAR(length=10),
               type_=sa.String(length=12),
               existing_nullable=True)

    with op.batch_alter_table('movimiento_contable', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cierre_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_cierre', 'cierre_mensual', ['cierre_id'], ['id'])



def downgrade():
    with op.batch_alter_table('movimiento_contable', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cierre', type_='foreignkey')
        batch_op.drop_column('cierre_id')

    with op.batch_alter_table('cierre_mensual', schema=None) as batch_op:
        batch_op.alter_column('modo',
               existing_type=sa.String(length=12),
               type_=sa.VARCHAR(length=10),
               existing_nullable=True)
        batch_op.drop_column('ganancia')
        batch_op.drop_column('repago')
        batch_op.drop_column('colchon_entrante')
        batch_op.drop_column('egresos')
        batch_op.drop_column('ingresos')

    with op.batch_alter_table('aporte_capital', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cierre', type_='foreignkey')
        batch_op.drop_column('cierre_id')

    op.drop_table('cierre_socio')
