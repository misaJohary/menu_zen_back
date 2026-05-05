# Messaging & Call Feature — Implementation Plan

## Context

Add real-time **messaging** and **voice (audio) calls** between users of the same
restaurant. **Video is out of scope** — calls are audio-only. Conversations can be:

- **Direct** (1:1 between two users)
- **Group** (3+ users — e.g. "Servers", "Kitchen team")

Calls reuse the same conversation entity (a call always happens *inside* a
conversation). The backend acts as:

- **Persistence layer** for messages and call history (REST)
- **Signaling server** for real-time delivery (WebSocket)

Media for calls is **not** relayed by the backend. We use **WebRTC** so the
audio flows peer-to-peer (or via a TURN server we configure later); the
backend only carries SDP offers/answers and ICE candidates.

### Conventions to follow

- SQLModel ORM models in [app/models/models.py](app/models/models.py), base schemas imported from [app/schemas/](app/schemas/)
- Pydantic base schemas in [app/schemas/](app/schemas/) (one file per feature)
- FastAPI router in [app/routers/](app/routers/)
- Alembic migration for every DB change
- WebSocket connection lifecycle managed by a `ConnectionManager` (mirror [app/services/ws_service.py](app/services/ws_service.py))
- Permission checks via [`require_permission()`](app/cores/permissions.py)
- Restaurant scoping: a user's conversations are bounded by `restaurant_id` (no cross-restaurant chat)

---

## Step 1 — RBAC: new permissions ✅

Add to `_ALL_PERMISSIONS` in [app/main.py](app/main.py):

```python
("messages", "read"),
("messages", "create"),
("messages", "delete"),     # delete own message
("conversations", "create"),
("conversations", "read"),
("conversations", "update"), # rename group, add/remove members
("calls", "create"),         # initiate call
("calls", "read"),           # see call history
```

Add to `_ROLE_PERMISSIONS`:

- `super_admin`, `admin` — all of the above
- `cashier`, `server`, `cook` — `messages:*`, `conversations:create/read/update`, `calls:create/read`

Rationale: every authenticated employee should be able to chat and call
colleagues. Admins keep the moderation actions implicitly via "delete any
message" handled in the router (level check).

---

## Step 2 — Schemas (`app/schemas/conversation_schemas.py`) ✅

New file. Holds enums + `Base` classes that the ORM models will subclass.

```python
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
    SYSTEM = "system"        # "X added Y", "call started", etc.
    CALL_EVENT = "call_event"


class ConversationBase(SQLModel):
    restaurant_id: Optional[int] = None        # set from current_user
    type: ConversationType = ConversationType.DIRECT
    name: Optional[str] = None                 # required for GROUP, null for DIRECT
    created_by_id: Optional[int] = None


class ConversationCreate(SQLModel):
    type: ConversationType
    name: Optional[str] = None
    participant_ids: List[int]                 # excluding the creator (auto-added)


class ConversationUpdate(SQLModel):
    name: Optional[str] = None                 # rename group


class ParticipantPublic(SQLModel):
    user_id: int
    username: str
    full_name: Optional[str]
    joined_at: datetime
    last_read_message_id: Optional[int]
    is_admin: bool


class ConversationPublic(SQLModel):
    id: int
    type: ConversationType
    name: Optional[str]
    created_by_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    participants: List[ParticipantPublic] = []
    last_message: Optional["MessagePublic"] = None
    unread_count: int = 0


class MessageBase(SQLModel):
    conversation_id: Optional[int] = None
    sender_id: Optional[int] = None
    type: MessageType = MessageType.TEXT
    content: Optional[str] = None              # text body or caption
    attachment_url: Optional[str] = None       # for IMAGE/FILE
    attachment_name: Optional[str] = None
    reply_to_id: Optional[int] = None


class MessageCreate(SQLModel):
    type: MessageType = MessageType.TEXT
    content: Optional[str] = None
    attachment_url: Optional[str] = None
    attachment_name: Optional[str] = None
    reply_to_id: Optional[int] = None


class MessagePublic(MessageBase):
    id: int
    created_at: datetime
    edited_at: Optional[datetime]
    deleted_at: Optional[datetime]
    sender_username: Optional[str] = None      # populated in router
```

## Step 3 — Schemas (`app/schemas/call_schemas.py`) ✅

New file.

```python
from datetime import datetime
from enum import Enum
from typing import List, Optional
from sqlmodel import SQLModel


class CallStatus(str, Enum):
    RINGING = "ringing"        # initiated, no one accepted yet
    ACTIVE = "active"          # at least 2 participants joined
    ENDED = "ended"
    MISSED = "missed"          # nobody accepted before timeout
    DECLINED = "declined"      # explicitly declined by callee (1:1 only)


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


class CallPublic(SQLModel):
    id: int
    conversation_id: int
    status: CallStatus
    started_by_id: int
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    participants: List["CallParticipantPublic"] = []


class CallParticipantPublic(SQLModel):
    user_id: int
    username: Optional[str]
    state: CallParticipantState
    joined_at: Optional[datetime]
    left_at: Optional[datetime]
```

---

## Step 4 — ORM models (`app/models/models.py`) ✅

Add at the top:

```python
from app.schemas.conversation_schemas import (
    ConversationBase, ConversationType,
    MessageBase, MessageType,
)
from app.schemas.call_schemas import (
    CallSessionBase, CallParticipantBase,
    CallStatus, CallParticipantState,
)
```

Add to `User`:

```python
sent_messages: List["Message"] = Relationship(back_populates="sender")
conversation_links: List["ConversationParticipant"] = Relationship(back_populates="user")
call_links: List["CallParticipant"] = Relationship(back_populates="user")
```

### 4a. `Conversation`

```python
class Conversation(ConversationBase, table=True):
    __tablename__ = "conversation"

    id: Optional[int] = Field(default=None, primary_key=True)
    restaurant_id: Optional[int] = Field(default=None, foreign_key="restaurant.id", ondelete="CASCADE")
    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    participants: List["ConversationParticipant"] = Relationship(
        back_populates="conversation", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    messages: List["Message"] = Relationship(back_populates="conversation")
    calls: List["CallSession"] = Relationship(back_populates="conversation")
```

### 4b. `ConversationParticipant`

```python
class ConversationParticipant(SQLModel, table=True):
    __tablename__ = "conversation_participant"

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", ondelete="CASCADE")
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE")
    joined_at: datetime = Field(default_factory=datetime.now)
    left_at: Optional[datetime] = None
    is_admin: bool = Field(default=False)              # group admin (creator by default)
    last_read_message_id: Optional[int] = Field(default=None, foreign_key="message.id")
    muted: bool = Field(default=False)

    conversation: Optional[Conversation] = Relationship(back_populates="participants")
    user: Optional[User] = Relationship(back_populates="conversation_links")

    class Config:
        table_args = (UniqueConstraint("conversation_id", "user_id", name="uq_conv_user"),)
```

### 4c. `Message`

```python
class Message(MessageBase, table=True):
    __tablename__ = "message"

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", ondelete="CASCADE")
    sender_id: Optional[int] = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    reply_to_id: Optional[int] = Field(default=None, foreign_key="message.id", ondelete="SET NULL")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None              # soft delete

    conversation: Optional[Conversation] = Relationship(back_populates="messages")
    sender: Optional[User] = Relationship(back_populates="sent_messages")
    reply_to: Optional["Message"] = Relationship(
        sa_relationship_kwargs={"remote_side": "Message.id"}
    )
```

### 4d. `CallSession`

```python
class CallSession(CallSessionBase, table=True):
    __tablename__ = "call_session"

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", ondelete="CASCADE")
    started_by_id: Optional[int] = Field(default=None, foreign_key="user.id", ondelete="SET NULL")

    conversation: Optional[Conversation] = Relationship(back_populates="calls")
    participants: List["CallParticipant"] = Relationship(
        back_populates="call", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
```

### 4e. `CallParticipant`

```python
class CallParticipant(CallParticipantBase, table=True):
    __tablename__ = "call_participant"

    id: Optional[int] = Field(default=None, primary_key=True)
    call_id: int = Field(foreign_key="call_session.id", ondelete="CASCADE")
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE")

    call: Optional[CallSession] = Relationship(back_populates="participants")
    user: Optional[User] = Relationship(back_populates="call_links")

    class Config:
        table_args = (UniqueConstraint("call_id", "user_id", name="uq_call_user"),)
```

---

## Step 5 — Alembic migration ✅

```bash
alembic revision --autogenerate -m "add messaging and call feature"
alembic upgrade head
```

Verify the generated script creates: `conversation`, `conversation_participant`,
`message`, `call_session`, `call_participant`. Add explicit indexes:

- `message(conversation_id, created_at DESC)` — pagination
- `conversation_participant(user_id)` — "my conversations" lookup
- `call_session(conversation_id, started_at DESC)`

If autogenerate misses anything (it sometimes does for `ondelete`), patch the
script manually before `upgrade`.

---

## Step 6 — Connection manager (`app/services/chat_ws_service.py`)

The existing [`ConnectionManager`](app/services/ws_service.py) is keyed by
`restaurant_id`. Messaging needs **per-user** routing (one user can be on phone
+ desktop) and **per-conversation broadcast**.

Create a new `ChatConnectionManager` that:

```python
class ChatConnectionManager:
    # user_id -> set of WebSocket (one user can have many tabs/devices)
    user_sockets: Dict[int, Set[WebSocket]]
    socket_user: Dict[WebSocket, int]

    async def connect(ws, user_id): ...
    def disconnect(ws): ...

    async def send_to_user(user_id: int, payload: dict): ...
    async def send_to_users(user_ids: list[int], payload: dict): ...
    async def broadcast_to_conversation(conv_id: int, payload: dict, db: Session, exclude_user_id: int | None = None):
        # look up participants from DB, fan out to each
        ...

    def is_online(user_id: int) -> bool: ...
    def online_users() -> set[int]: ...
```

Singleton pattern + `Depends(get_chat_connection_manager)`, mirroring the
existing service.

---

## Step 7 — REST router (`app/routers/conversations.py`)

```python
router = APIRouter(prefix="/conversations", tags=["conversations"],
                   dependencies=[Depends(get_current_active_user)])
```

Endpoints:

| Method | Path                                          | Permission              | Purpose |
| ------ | --------------------------------------------- | ----------------------- | ------- |
| POST   | `/conversations`                              | `conversations:create`  | Create direct or group. For DIRECT, return existing one if it already exists between the two users. |
| GET    | `/conversations`                              | `conversations:read`    | List my conversations (last message + unread count, paginated). |
| GET    | `/conversations/{id}`                         | `conversations:read`    | Detail + participants. Verify caller is a participant. |
| PATCH  | `/conversations/{id}`                         | `conversations:update`  | Rename group (admin only). |
| POST   | `/conversations/{id}/participants`            | `conversations:update`  | Add users to a group (admin only). Emits SYSTEM message. |
| DELETE | `/conversations/{id}/participants/{user_id}`  | `conversations:update`  | Remove user / leave group. |
| GET    | `/conversations/{id}/messages`                | `messages:read`         | Paginated history (`?before_id=…&limit=50`). |
| POST   | `/conversations/{id}/messages`                | `messages:create`       | Send message. Persists then broadcasts via WS. |
| PATCH  | `/messages/{id}`                              | `messages:create`       | Edit own message. |
| DELETE | `/messages/{id}`                              | `messages:delete`       | Soft-delete (own message, or admin). |
| POST   | `/conversations/{id}/read`                    | `messages:read`         | Mark messages up to `last_message_id` read. |
| POST   | `/messages/upload`                            | `messages:create`       | Multipart upload → returns URL for `attachment_url`. Stored under `uploads/chat/`. |

Authorization helper used everywhere:

```python
def _require_participant(conv_id: int, user_id: int, db: Session) -> ConversationParticipant: ...
```

When sending a message:

1. Persist `Message`.
2. Update `Conversation.updated_at`.
3. Build `MessagePublic` payload.
4. `await chat_manager.broadcast_to_conversation(conv_id, {"type": "message.new", "data": payload}, db)`.
5. Return the persisted message in the HTTP response.

---

## Step 8 — REST router (`app/routers/calls.py`)

| Method | Path                          | Permission         | Purpose |
| ------ | ----------------------------- | ------------------ | ------- |
| POST   | `/calls`                      | `calls:create`     | Start an audio call in a conversation. Creates `CallSession` + `CallParticipant` rows (caller=JOINED, others=INVITED). Broadcasts `call.incoming` over WS. |
| POST   | `/calls/{id}/accept`          | `calls:create`     | Mark caller's `CallParticipant.state=JOINED`. Broadcasts `call.accepted`. Triggers status `ACTIVE`. |
| POST   | `/calls/{id}/decline`         | `calls:create`     | `state=DECLINED`. If 1:1 → `CallStatus.DECLINED + ENDED`. |
| POST   | `/calls/{id}/leave`           | `calls:create`     | `state=LEFT, left_at=now`. If no JOINED participants left → `CallStatus.ENDED, ended_at=now`. |
| GET    | `/conversations/{id}/calls`   | `calls:read`       | Call history per conversation. |
| GET    | `/calls/{id}`                 | `calls:read`       | Call detail. |

Notes:
- A 30s server-side timeout (background task or scheduled check) flips `RINGING` calls with no `JOINED` participants to `MISSED`.
- Every transition broadcasts a structured WS event to all conversation participants so UIs stay in sync.

---

## Step 9 — WebSocket signaling (`app/routers/chat_ws.py`)

One persistent WebSocket per logged-in user, used for:

1. **Inbound notifications** — server → client (new message, new call, call state change, typing, presence)
2. **WebRTC signaling** — client A → server → client B (offer / answer / ICE candidates)
3. **Lightweight client events** — typing, read receipts, ping

Endpoint:

```
GET /ws/chat?token=<JWT>
```

Authenticate by parsing the token from the query string (WebSockets don't carry
`Authorization` headers easily). Resolve `current_user`, then
`chat_manager.connect(ws, user_id)`.

### Server → client event envelope

```json
{ "type": "message.new",
  "data": { ...MessagePublic... } }
```

Event types:

| Type                   | Payload                                                 |
| ---------------------- | ------------------------------------------------------- |
| `message.new`          | Full `MessagePublic`                                    |
| `message.edited`       | `MessagePublic`                                         |
| `message.deleted`      | `{ id, conversation_id }`                               |
| `message.read`         | `{ conversation_id, user_id, last_read_message_id }`    |
| `conversation.created` | `ConversationPublic`                                    |
| `conversation.updated` | `ConversationPublic`                                    |
| `conversation.member_added` / `member_removed` | `{ conversation_id, user_id }`  |
| `presence.online` / `presence.offline`         | `{ user_id }`                   |
| `typing.start` / `typing.stop` | `{ conversation_id, user_id }`                  |
| `call.incoming`        | `CallPublic` (sent only to invitees)                    |
| `call.accepted` / `call.declined` / `call.ended` | `CallPublic`                  |
| `call.participant_joined` / `participant_left` | `{ call_id, user_id }`          |
| `call.signal`          | `{ call_id, from_user_id, to_user_id, kind: "offer"\|"answer"\|"ice", payload }` |

### Client → server event envelope

```json
{ "type": "typing.start",
  "data": { "conversation_id": 12 } }
```

Accepted client types:

- `ping` → server replies `pong` (heartbeat, every 30s)
- `typing.start` / `typing.stop` → fanned out to other participants
- `signal` → `{ call_id, to_user_id, kind, payload }`. Server validates that
  both users are participants of the call, then forwards as `call.signal`.

### Why signaling only?

We never decode media. The peers exchange SDP + ICE through us; once they have
each other's candidates, audio flows direct (or via a STUN/TURN server
configured in the client). This keeps the backend cheap.

---

## Step 10 — Wire routers + WS into `main.py`

In [app/main.py](app/main.py):

```python
from app.routers import conversations, calls, chat_ws
...
app.include_router(conversations.router)
app.include_router(calls.router)
app.include_router(chat_ws.router)
```

Mount uploads (already done) — chat attachments live under `uploads/chat/`.

---

## Step 11 — Permission seeding

After editing `_ALL_PERMISSIONS` and `_ROLE_PERMISSIONS` in `main.py`, the
`seed_rbac()` function will auto-insert the new rows on next startup (idempotent).
No manual SQL needed.

---

## Step 12 — Tests (`tests/`)

Add pytest cases (mirror existing test style):

1. `test_conversations.py`
   - Create direct conversation — second create returns the same one
   - Create group with 3 members, rename, add/remove member
   - Non-participant cannot read `/messages`
2. `test_messages.py`
   - Send text message → appears in history
   - Edit, delete (soft) — `deleted_at` set, content nulled in public schema
   - Read-receipt updates `last_read_message_id` and unread count
3. `test_calls.py`
   - Start call → invitees see `RINGING`, `CallParticipant.INVITED`
   - Accept → `ACTIVE`; leave → `ENDED` when last participant leaves
   - 1:1 decline ends the call
4. `test_chat_ws.py`
   - Two clients on same conversation: client A sends, client B receives
   - Signaling forward (offer/answer/ice) only delivered to the named callee
   - Disconnect cleans up `user_sockets` entry

Use `httpx.AsyncClient` for REST and `fastapi.testclient.TestClient.websocket_connect`
for WS.

---

## Step 13 — Frontend integration notes (out of scope, for reference)

Not part of this backend change — listed so the API surface is sufficient:

- Client opens a single `/ws/chat` connection on login.
- Conversation list comes from `GET /conversations`; opens detail screen with
  history page from `GET /conversations/{id}/messages?before_id=…`.
- Sending a message is a `POST` (returns the message); the same message also
  arrives via WS for other participants and for other devices of the sender.
- For calls, the client uses **WebRTC** (`RTCPeerConnection`) with audio-only
  tracks. After `POST /calls`, it listens for `call.accepted` then exchanges
  `signal` events through the WS.
- A STUN server (`stun.l.google.com:19302` is fine to start) is enough for LAN
  / same-restaurant scenarios. Add a TURN server later if remote staff joins
  from restrictive networks.

---

## Rollout order

1. Step 1 (permissions in `main.py` — no DB change yet, just additions)
2. Steps 2–4 (schemas + ORM models)
3. Step 5 (Alembic migration; verify `alembic upgrade head` on a backup of `database.db`)
4. Step 6 (chat connection manager — pure in-memory, no API surface)
5. Steps 7–8 (REST routers — testable via Swagger before any WS work)
6. Step 9 (WS endpoint and signaling)
7. Step 10 (wire into `main.py`)
8. Step 12 (tests, run after each step ideally)

Each step is independently mergeable; calls (Steps 8 + signaling subset of 9)
can ship after messaging is live.
