"""extend order for customer app

Revision ID: 609037c1b399
Revises: 73963677fce7
Create Date: 2026-05-11 13:30:05.124828

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '609037c1b399'
down_revision: Union[str, Sequence[str], None] = '73963677fce7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    order_type_enum = sa.Enum('DINE_IN', 'PICKUP', 'DELIVERY', name='ordertype')
    order_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'order',
        sa.Column('order_type', order_type_enum, nullable=True),
    )
    op.add_column('order', sa.Column('customer_id', sa.Integer(), nullable=True))
    op.add_column('order', sa.Column('contact_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('order', sa.Column('contact_phone', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('order', sa.Column('scheduled_for', sa.DateTime(), nullable=True))
    op.add_column('order', sa.Column('restaurant_id', sa.Integer(), nullable=True))

    # Backfill order_type for existing rows. Postgres stores enum members by
    # their declared *name*, so we use 'DINE_IN' (not 'dine_in').
    op.execute("UPDATE \"order\" SET order_type = 'DINE_IN' WHERE order_type IS NULL;")
    op.alter_column('order', 'order_type', nullable=False)

    # Backfill restaurant_id from the order's table for existing staff rows so
    # the new column is useful immediately. Customer orders will set it on
    # creation.
    op.execute(
        """
        UPDATE "order" o
           SET restaurant_id = rt.restaurant_id
          FROM restaurant_table rt
         WHERE rt.id = o.restaurant_table_id
           AND o.restaurant_id IS NULL
        """
    )

    op.alter_column(
        'order', 'restaurant_table_id',
        existing_type=sa.INTEGER(),
        nullable=True,
    )
    op.create_foreign_key(
        'fk_order_restaurant_id',
        'order', 'restaurant',
        ['restaurant_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_foreign_key(
        'fk_order_customer_id',
        'order', 'customer',
        ['customer_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_order_customer_id', 'order', type_='foreignkey')
    op.drop_constraint('fk_order_restaurant_id', 'order', type_='foreignkey')
    op.alter_column(
        'order', 'restaurant_table_id',
        existing_type=sa.INTEGER(),
        nullable=False,
    )
    op.drop_column('order', 'restaurant_id')
    op.drop_column('order', 'scheduled_for')
    op.drop_column('order', 'contact_phone')
    op.drop_column('order', 'contact_name')
    op.drop_column('order', 'customer_id')
    op.drop_column('order', 'order_type')
    sa.Enum(name='ordertype').drop(op.get_bind(), checkfirst=True)
