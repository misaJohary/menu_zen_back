"""add delivery fields to order

Revision ID: a7f3c8e9b5d4
Revises: e1f5a7b2c8d3
Create Date: 2026-05-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a7f3c8e9b5d4'
down_revision: Union[str, Sequence[str], None] = 'e1f5a7b2c8d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'order',
        sa.Column('delivery_address', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        'order',
        sa.Column('delivery_notes', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('order', 'delivery_notes')
    op.drop_column('order', 'delivery_address')
