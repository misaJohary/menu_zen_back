"""add kitchen_note and tracking_token to order

Revision ID: d9e2f1a3b7c8
Revises: a7f3c8e9b5d4
Create Date: 2026-05-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd9e2f1a3b7c8'
down_revision: Union[str, Sequence[str], None] = 'a7f3c8e9b5d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — guest dine-in order support."""
    op.add_column(
        'order',
        sa.Column('kitchen_note', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    )
    op.add_column(
        'order',
        sa.Column('tracking_token', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
    )
    op.create_index(
        'customer_orders_tracking_token_idx',
        'order',
        ['tracking_token'],
        unique=True,
        postgresql_where=sa.text('tracking_token IS NOT NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('customer_orders_tracking_token_idx', table_name='order')
    op.drop_column('order', 'tracking_token')
    op.drop_column('order', 'kitchen_note')
