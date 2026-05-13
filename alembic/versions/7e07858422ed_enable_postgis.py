"""enable postgis

Revision ID: 7e07858422ed
Revises: 8a3b74b733b1
Create Date: 2026-05-11 11:57:41.892991

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '7e07858422ed'
down_revision: Union[str, Sequence[str], None] = '8a3b74b733b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")


def downgrade() -> None:
    """Downgrade schema."""
    # No-op: do not drop the postgis extension on downgrade — other tables
    # may depend on it.
    pass
