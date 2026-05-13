"""add customer id and restaurant id and party size to reservation

Revision ID: 73963677fce7
Revises: d903deeaa17e
Create Date: 2026-05-11 13:19:54.615095

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '73963677fce7'
down_revision: Union[str, Sequence[str], None] = 'd903deeaa17e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('reservation', sa.Column('customer_id', sa.Integer(), nullable=True))
    op.add_column('reservation', sa.Column('restaurant_id', sa.Integer(), nullable=True))
    op.add_column('reservation', sa.Column('party_size', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_reservation_customer_id'), 'reservation', ['customer_id'], unique=False)
    op.create_index(op.f('ix_reservation_restaurant_id'), 'reservation', ['restaurant_id'], unique=False)
    op.create_foreign_key(
        'fk_reservation_customer_id',
        'reservation', 'customer',
        ['customer_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_reservation_restaurant_id',
        'reservation', 'restaurant',
        ['restaurant_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_reservation_restaurant_id', 'reservation', type_='foreignkey')
    op.drop_constraint('fk_reservation_customer_id', 'reservation', type_='foreignkey')
    op.drop_index(op.f('ix_reservation_restaurant_id'), table_name='reservation')
    op.drop_index(op.f('ix_reservation_customer_id'), table_name='reservation')
    op.drop_column('reservation', 'party_size')
    op.drop_column('reservation', 'restaurant_id')
    op.drop_column('reservation', 'customer_id')
