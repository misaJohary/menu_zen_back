"""add server to order

Revision ID: 1fae30353695
Revises: a914dffe5473
Create Date: 2025-08-05 21:39:50.297368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1fae30353695'
down_revision: Union[str, Sequence[str], None] = 'a914dffe5473'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass            # target column (assuming 'id' is the primary key)
    
    # ### end Alembic commands ###

def downgrade() -> None:
    # ### end Alembic commands ###
    pass