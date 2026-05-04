from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import SQLModel


class CallStatus(str, Enum):
    RINGING = "ringing"
    ACTIVE = "active"
    ENDED = "ended"
    MISSED = "missed"
    DECLINED = "declined"


class CallParticipantState(str, Enum):
    INVITED = "invited"
    JOINED = "joined"
    LEFT = "left"
    DECLINED = "declined"


class CallSessionBase(SQLModel):
    conversation_id: Optional[int] = None
    status: CallStatus = CallStatus.RINGING
    started_by_id: Optional[int] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class CallParticipantBase(SQLModel):
    call_id: Optional[int] = None
    user_id: Optional[int] = None
    state: CallParticipantState = CallParticipantState.INVITED
    joined_at: Optional[datetime] = None
    left_at: Optional[datetime] = None


class CallStartRequest(SQLModel):
    conversation_id: int


class CallParticipantPublic(SQLModel):
    user_id: int
    username: Optional[str] = None
    state: CallParticipantState
    joined_at: Optional[datetime] = None
    left_at: Optional[datetime] = None


class CallPublic(SQLModel):
    id: int
    conversation_id: int
    status: CallStatus
    started_by_id: Optional[int] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    participants: List[CallParticipantPublic] = []


class CallSignalPayload(SQLModel):
    call_id: int
    to_user_id: int
    kind: str  # "offer" | "answer" | "ice"
    payload: dict


CallPublic.model_rebuild()
