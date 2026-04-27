"""add_updated_at_to_restaurant_table

Revision ID: 225fb63d9242
Revises: 71f09edd9636
Create Date: 2026-04-22 09:57:12.164389

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '225fb63d9242'
down_revision: Union[str, Sequence[str], None] = '71f09edd9636'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table('restaurant_table', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ))
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table('restaurant_table', schema=None) as batch_op:
        batch_op.drop_column('updated_at')
    op.execute("PRAGMA foreign_keys=ON")
