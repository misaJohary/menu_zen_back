"""add oncascade delete order menu item

Revision ID: 680e3860dc2e
Revises: 09549a320d43
Create Date: 2025-08-28 17:02:29.079761

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '680e3860dc2e'
down_revision: Union[str, Sequence[str], None] = '09549a320d43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('ordermenuitem', schema=None) as batch_op:
        # Drop the column and recreate it as nullable first
        batch_op.drop_column('order_id')
        batch_op.add_column(sa.Column('order_id', sa.Integer(), nullable=True))
    
    # Now populate the order_id column with existing data if needed
    # You might need to add logic here to set appropriate order_id values
    
    # Then make it non-nullable and add the foreign key constraint
    with op.batch_alter_table('ordermenuitem', schema=None) as batch_op:
        batch_op.alter_column('order_id', nullable=False)
        batch_op.create_foreign_key('fk_ordermenuitem_order_id', 'order', ['order_id'], ['id'], ondelete='CASCADE')

def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ordermenuitem', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ordermenuitem_order_id', type_='foreignkey')
        batch_op.drop_column('order_id')
        batch_op.add_column(sa.Column('order_id', sa.Integer(), nullable=True))
        batch_op.alter_column('order_id', nullable=False)
        batch_op.create_foreign_key('fk_ordermenuitem_order_original', 'order', ['order_id'], ['id'])
