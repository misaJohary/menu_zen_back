"""add opening hours to restaurant

Revision ID: 8b1f4d2a9c10
Revises: 609037c1b399
Create Date: 2026-05-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b1f4d2a9c10'
down_revision: Union[str, Sequence[str], None] = '609037c1b399'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'restaurant',
        sa.Column('opening_hours', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('restaurant', 'opening_hours')
