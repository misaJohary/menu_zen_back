"""add max_concurrent_guests to restaurant

Revision ID: c4d3e2b1a0f9
Revises: 8b1f4d2a9c10
Create Date: 2026-05-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d3e2b1a0f9'
down_revision: Union[str, Sequence[str], None] = '8b1f4d2a9c10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'restaurant',
        sa.Column('max_concurrent_guests', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('restaurant', 'max_concurrent_guests')
