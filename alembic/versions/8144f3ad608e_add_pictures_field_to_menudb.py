"""Add pictures field to MenuDB

Revision ID: 8144f3ad608e
Revises: 
Create Date: 2025-07-29 16:33:28.157183

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8144f3ad608e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    


def downgrade() -> None:
    """Downgrade schema."""
    pass
