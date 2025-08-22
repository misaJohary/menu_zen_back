"""add active to menu

Revision ID: 295ced27eb87
Revises: 1fae30353695
Create Date: 2025-08-15 15:15:43.122670

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '295ced27eb87'
down_revision: Union[str, Sequence[str], None] = '1fae30353695'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('menu', sa.Column('is_active', sa.BOOLEAN))
    pass


def downgrade() -> None:
    op.drop_column('menu', 'is_active')
    pass
