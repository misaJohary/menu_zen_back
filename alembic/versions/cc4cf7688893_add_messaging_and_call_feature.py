"""add messaging and call feature

Revision ID: cc4cf7688893
Revises: 225fb63d9242
Create Date: 2026-04-28 16:32:28.559148

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'cc4cf7688893'
down_revision: Union[str, Sequence[str], None] = '225fb63d9242'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'conversation',
        sa.Column('type', sa.Enum('DIRECT', 'GROUP', name='conversationtype'), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurant.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'message',
        sa.Column('type', sa.Enum('TEXT', 'IMAGE', 'FILE', 'SYSTEM', 'CALL_EVENT', name='messagetype'), nullable=False),
        sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('attachment_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('attachment_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=True),
        sa.Column('reply_to_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('edited_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reply_to_id'], ['message.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sender_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_message_conversation_id_created_at',
        'message',
        ['conversation_id', sa.text('created_at DESC')],
        unique=False,
    )

    op.create_table(
        'conversation_participant',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.Column('left_at', sa.DateTime(), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('last_read_message_id', sa.Integer(), nullable=True),
        sa.Column('muted', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['last_read_message_id'], ['message.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'user_id', name='uq_conv_user'),
    )
    op.create_index(
        'ix_conversation_participant_user_id',
        'conversation_participant',
        ['user_id'],
        unique=False,
    )

    op.create_table(
        'call_session',
        sa.Column('status', sa.Enum('RINGING', 'ACTIVE', 'ENDED', 'MISSED', 'DECLINED', name='callstatus'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('started_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['started_by_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_call_session_conversation_id_started_at',
        'call_session',
        ['conversation_id', sa.text('started_at DESC')],
        unique=False,
    )

    op.create_table(
        'call_participant',
        sa.Column('state', sa.Enum('INVITED', 'JOINED', 'LEFT', 'DECLINED', name='callparticipantstate'), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=True),
        sa.Column('left_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('call_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['call_session.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('call_id', 'user_id', name='uq_call_user'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_call_session_conversation_id_started_at', table_name='call_session')
    op.drop_table('call_participant')
    op.drop_table('call_session')
    op.drop_index('ix_conversation_participant_user_id', table_name='conversation_participant')
    op.drop_table('conversation_participant')
    op.drop_index('ix_message_conversation_id_created_at', table_name='message')
    op.drop_table('message')
    op.drop_table('conversation')
