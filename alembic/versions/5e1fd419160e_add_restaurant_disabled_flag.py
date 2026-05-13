"""add restaurant disabled flag

Revision ID: 5e1fd419160e
Revises: 7160a8a79a36
Create Date: 2026-05-11 12:08:37.038230

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5e1fd419160e'
down_revision: Union[str, Sequence[str], None] = '7160a8a79a36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'restaurant',
        sa.Column('disabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Drop the server default so the column is purely application-controlled
    # going forward (matches the SQLModel definition).
    op.alter_column('restaurant', 'disabled', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('restaurant', 'disabled')
