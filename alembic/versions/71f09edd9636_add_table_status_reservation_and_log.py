"""add_table_status_reservation_and_log

Revision ID: 71f09edd9636
Revises: f42ea389ff5f
Create Date: 2026-04-21 11:07:05.422134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '71f09edd9636'
down_revision: Union[str, Sequence[str], None] = 'f42ea389ff5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'reservation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('phone', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('reserved_at', sa.DateTime(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'HONORED', 'CANCELLED', 'NO_SHOW', name='reservationstatus'),
            nullable=False,
            server_default='ACTIVE',
        ),
        sa.Column('note', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'table_reservation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reservation_id', sa.Integer(), nullable=False),
        sa.Column('table_id', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'HONORED', 'CANCELLED', 'NO_SHOW', name='reservationstatus'),
            nullable=False,
            server_default='ACTIVE',
        ),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['reservation_id'], ['reservation.id']),
        sa.ForeignKeyConstraint(['table_id'], ['restaurant_table.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_table_reservation_table_id_status',
        'table_reservation',
        ['table_id', 'status'],
    )
    op.create_index(
        'ix_table_reservation_reservation_id',
        'table_reservation',
        ['reservation_id'],
    )

    op.create_table(
        'table_status_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('table_id', sa.Integer(), nullable=False),
        sa.Column('changed_by_id', sa.Integer(), nullable=True),
        sa.Column(
            'old_status',
            sa.Enum('FREE', 'RESERVED', 'WAITING', 'ASSIGNED', name='tablestatus'),
            nullable=False,
        ),
        sa.Column(
            'new_status',
            sa.Enum('FREE', 'RESERVED', 'WAITING', 'ASSIGNED', name='tablestatus'),
            nullable=False,
        ),
        sa.Column('changed_at', sa.DateTime(), nullable=False),
        sa.Column('note', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(['changed_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['table_id'], ['restaurant_table.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table('restaurant_table', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'status',
            sa.Enum('FREE', 'RESERVED', 'WAITING', 'ASSIGNED', name='tablestatus'),
            nullable=False,
            server_default='FREE',
        ))
        batch_op.add_column(sa.Column('server_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('waiting_since', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('seats', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_restaurant_table_server_id_user',
            'user',
            ['server_id'],
            ['id'],
        )
    op.execute("PRAGMA foreign_keys=ON")

    # Index to keep the auto-release EXISTS query fast (see Step 10 in the plan)
    op.create_index(
        'ix_order_restaurant_table_id_payment_status',
        'order',
        ['restaurant_table_id', 'payment_status'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_order_restaurant_table_id_payment_status', table_name='order')

    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table('restaurant_table', schema=None) as batch_op:
        batch_op.drop_constraint('fk_restaurant_table_server_id_user', type_='foreignkey')
        batch_op.drop_column('seats')
        batch_op.drop_column('waiting_since')
        batch_op.drop_column('server_id')
        batch_op.drop_column('status')
    op.execute("PRAGMA foreign_keys=ON")

    op.drop_table('table_status_log')
    op.drop_index('ix_table_reservation_reservation_id', table_name='table_reservation')
    op.drop_index('ix_table_reservation_table_id_status', table_name='table_reservation')
    op.drop_table('table_reservation')
    op.drop_table('reservation')
