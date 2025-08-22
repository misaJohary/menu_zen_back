"""add restaurant id foreign key to menu item

Revision ID: 69212d4cd99e
Revises: c9ff5ff8e147
Create Date: 2025-08-19 22:04:23.891256

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '69212d4cd99e'
down_revision: Union[str, Sequence[str], None] = 'c9ff5ff8e147'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("menu_item", schema=None) as batch_op:
        batch_op.add_column(sa.Column("restaurant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_menu_item_restaurant",  # give it a name
            "restaurant",
            ["restaurant_id"],
            ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("menu_item", schema=None) as batch_op:
        batch_op.drop_constraint("fk_menu_item_restaurant", type_="foreignkey")
        batch_op.drop_column("restaurant_id")