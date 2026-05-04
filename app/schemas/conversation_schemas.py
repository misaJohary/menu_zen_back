from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import SQLModel


class ConversationType(str, Enum):
    DIRECT = "direct"
    GROUP = "group"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    SYSTEM = "system"
    CALL_EVENT = "call_event"


class ConversationBase(SQLModel):
    restaurant_id: Optional[int] = None
    type: ConversationType = ConversationType.DIRECT
    name: Optional[str] = None
    created_by_id: Optional[int] = None


class ConversationCreate(SQLModel):
    type: ConversationType
    name: Optional[str] = None
    participant_ids: List[int]


class ConversationUpdate(SQLModel):
    name: Optional[str] = None


class ConversationAddParticipants(SQLModel):
    user_ids: List[int]


class ParticipantPublic(SQLModel):
    user_id: int
    username: str
    full_name: Optional[str] = None
    joined_at: datetime
    last_read_message_id: Optional[int] = None
    is_admin: bool = False


class MessageBase(SQLModel):
    conversation_id: Optional[int] = None
    sender_id: Optional[int] = None
    type: MessageType = MessageType.TEXT
    content: Optional[str] = None
    attachment_url: Optional[str] = None
    attachment_name: Optional[str] = None
    reply_to_id: Optional[int] = None


class MessageCreate(SQLModel):
    type: MessageType = MessageType.TEXT
    content: Optional[str] = None
    attachment_url: Optional[str] = None
    attachment_name: Optional[str] = None
    reply_to_id: Optional[int] = None


class MessageUpdate(SQLModel):
    content: Optional[str] = None


class MessagePublic(MessageBase):
    id: int
    created_at: datetime
    edited_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    sender_username: Optional[str] = None


class ConversationPublic(SQLModel):
    id: int
    type: ConversationType
    name: Optional[str] = None
    created_by_id: Optional[int] = None
    restaurant_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    participants: List[ParticipantPublic] = []
    last_message: Optional[MessagePublic] = None
    unread_count: int = 0


class MarkReadRequest(SQLModel):
    last_message_id: int


ConversationPublic.model_rebuild()
