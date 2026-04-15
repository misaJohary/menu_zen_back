"""remove_kitchen_translations_add_name

Revision ID: f42ea389ff5f
Revises: 05617136c4f7
Create Date: 2026-04-15 14:54:48.328029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f42ea389ff5f'
down_revision: Union[str, Sequence[str], None] = '05617136c4f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('kitchen_translation')

    # Disable FK enforcement so SQLite batch mode can copy the kitchen table
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table('kitchen', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table('kitchen', schema=None) as batch_op:
        batch_op.drop_column('name')
    op.execute("PRAGMA foreign_keys=ON")

    op.create_table('kitchen_translation',
        sa.Column('language_code', sa.VARCHAR(length=7), nullable=False),
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('kitchen_id', sa.INTEGER(), nullable=True),
        sa.Column('name', sa.VARCHAR(length=100), nullable=False),
        sa.Column('description', sa.VARCHAR(length=500), nullable=True),
        sa.ForeignKeyConstraint(['kitchen_id'], ['kitchen.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
