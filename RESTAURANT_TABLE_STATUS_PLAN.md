# Restaurant Table Status Management — Implementation Plan

## Overview

Extend `RestaurantTable` to track table state through its lifecycle, assign servers,
record reservation details, log every status change, auto-release tables when payment
is complete, and broadcast all status changes over the existing WebSocket service.

---

## Proposed Status Names

| Status | Value | Description |
|---|---|---|
| Free | `free` | Table is empty and available |
| Reserved | `reserved` | Table is reserved (reservation details recorded) |
| Waiting | `waiting` | Clients are seated but no server has taken the table yet (timestamp recorded) |
| Assigned | `assigned` | A server has taken ownership of the table (server linked) |

---

## New Fields on `RestaurantTable`

| Field | Type | Notes |
|---|---|---|
| `status` | `TableStatus` enum | Default `free` |
| `server_id` | `Optional[int]` FK → `user.id` | Set when status → `assigned`; cleared on reset |
| `waiting_since` | `Optional[datetime]` | Set when status → `waiting`; cleared on reset |
| `reservation_name` | `Optional[str]` | Contact name for the reservation |
| `reservation_phone` | `Optional[str]` | Contact phone for the reservation |
| `reservation_at` | `Optional[datetime]` | Date and time of the planned reservation |

---

## New Model: `TableStatusLog`

Records every status change for audit and history purposes.

| Field | Type | Notes |
|---|---|---|
| `id` | `int` PK | Auto-increment |
| `table_id` | `int` FK → `restaurant_table.id` | The table that changed |
| `changed_by_id` | `Optional[int]` FK → `user.id` | User who triggered the change (null for system/auto) |
| `old_status` | `TableStatus` | Status before the change |
| `new_status` | `TableStatus` | Status after the change |
| `changed_at` | `datetime` | Timestamp of the change (`default_factory=datetime.now`) |
| `note` | `Optional[str]` | e.g., `"auto-released: all orders paid"` |

---

## Step-by-Step Implementation

### Step 1 — Define the `TableStatus` Enum

**File**: `app/schemas/restaurant_table_schemas.py`

Add a `TableStatus` string enum following the same pattern as `OrderStatus`:

```python
class TableStatus(str, Enum):
    FREE     = "free"
    RESERVED = "reserved"
    WAITING  = "waiting"
    ASSIGNED = "assigned"
```

---

### Step 2 — Update `RestaurantTableBase` and `RestaurantTable`

**File**: `app/models/models.py`

1. In `RestaurantTableBase` add the six new fields with safe defaults:
   - `status: TableStatus = TableStatus.FREE`
   - `server_id: Optional[int] = Field(default=None, foreign_key="user.id")`
   - `waiting_since: Optional[datetime] = Field(default=None)`
   - `reservation_name: Optional[str] = Field(default=None)`
   - `reservation_phone: Optional[str] = Field(default=None)`
   - `reservation_at: Optional[datetime] = Field(default=None)`

2. In `RestaurantTable` (the `table=True` class) add:
   - `server: Optional[User] = Relationship(back_populates="assigned_tables")`
   - `status_logs: List["TableStatusLog"] = Relationship(back_populates="table")`

3. On the `User` model add the reverse side:
   - `assigned_tables: List["RestaurantTable"] = Relationship(back_populates="server")`

> `server_id` references `user.id` — servers are users with the `server` role.

---

### Step 3 — Add the `TableStatusLog` Model

**File**: `app/models/models.py`

Add a new SQLModel table class **after** `RestaurantTable`:

```python
class TableStatusLog(SQLModel, table=True):
    __tablename__ = "table_status_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="restaurant_table.id")
    changed_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    old_status: TableStatus
    new_status: TableStatus
    changed_at: datetime = Field(default_factory=datetime.now)
    note: Optional[str] = Field(default=None)

    table: RestaurantTable = Relationship(back_populates="status_logs")
    changed_by: Optional[User] = Relationship()
```

---

### Step 4 — Update Schemas

**File**: `app/schemas/restaurant_table_schemas.py`

1. **`RestaurantTableBase`** — add the six new fields (same defaults as the model).

2. **`RestaurantTablePublic`** — extend to expose all new fields plus a nested server
   object `{ id, username }` so clients don't need a second request.

3. **`RestaurantTableStatusUpdate`** — narrow schema accepted by the status-change
   endpoint. The caller only sends `status` plus the reservation fields (only validated
   when `status == "reserved"`):

   ```python
   class RestaurantTableStatusUpdate(SQLModel):
       status: TableStatus
       reservation_name: Optional[str] = None   # required when status=reserved
       reservation_phone: Optional[str] = None  # required when status=reserved
       reservation_at: Optional[datetime] = None  # required when status=reserved
   ```

   Validate in the router (not the schema) that when `status == "reserved"` all three
   reservation fields are present; return HTTP 422 otherwise.

4. **`TableStatusLogPublic`** — response schema for the log endpoint:

   ```python
   class TableStatusLogPublic(SQLModel):
       id: int
       table_id: int
       changed_by_id: Optional[int]
       old_status: TableStatus
       new_status: TableStatus
       changed_at: datetime
       note: Optional[str]
   ```

---

### Step 5 — Business Rules for Status Transitions

Enforced in the router / service layer, **not** in the schema:

| Transition | Who can do it | Side effects on `RestaurantTable` |
|---|---|---|
| Any → `waiting` | Any authenticated user in the same restaurant | Set `waiting_since = now()`; clear `server_id`; clear reservation fields |
| Any → `assigned` | `server`, `admin`, `super_admin` | Set `server_id = current_user.id`; clear `waiting_since`; clear reservation fields |
| Any → `free` | `server`, `admin`, `super_admin` | Clear `server_id`, `waiting_since`, all reservation fields |
| Any → `reserved` | `admin`, `super_admin` | Set `reservation_name`, `reservation_phone`, `reservation_at` from body; clear `server_id`; clear `waiting_since` |

**Additional guard**: if the table is currently `assigned` and the caller's role is `server`,
only allow the transition if `current_user.id == table.server_id`. Admins bypass this.

**After every successful transition** (applies to all cases including auto-release):
1. Insert a `TableStatusLog` row with `old_status`, `new_status`, `changed_by_id`, and
   an optional `note`.
2. Broadcast a WebSocket event to the restaurant room (see Step 9).

---

### Step 6 — Alembic Migration

**File**: new file in `alembic/versions/` — generate with:
```bash
alembic revision --autogenerate -m "add_table_status_reservation_and_log"
```
Then verify and, if needed, hand-edit the generated file.

Because the project uses **SQLite**, all `ALTER TABLE` operations use `batch_alter_table`.

```python
def upgrade() -> None:
    # New columns on restaurant_table
    with op.batch_alter_table("restaurant_table", schema=None) as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(), nullable=False,
                                      server_default="free"))
        batch_op.add_column(sa.Column("server_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("waiting_since", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("reservation_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("reservation_phone", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("reservation_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_restaurant_table_server_id_user",
            "user", ["server_id"], ["id"]
        )

    # New table_status_log table
    op.create_table(
        "table_status_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("table_id", sa.Integer(), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), nullable=True),
        sa.Column("old_status", sa.String(), nullable=False),
        sa.Column("new_status", sa.String(), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["table_id"], ["restaurant_table.id"]),
        sa.ForeignKeyConstraint(["changed_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

def downgrade() -> None:
    op.drop_table("table_status_log")
    with op.batch_alter_table("restaurant_table", schema=None) as batch_op:
        batch_op.drop_constraint("fk_restaurant_table_server_id_user", type_="foreignkey")
        batch_op.drop_column("reservation_at")
        batch_op.drop_column("reservation_phone")
        batch_op.drop_column("reservation_name")
        batch_op.drop_column("waiting_since")
        batch_op.drop_column("server_id")
        batch_op.drop_column("status")
```

Run with: `alembic upgrade head`

---

### Step 7 — Add New Permissions

**File**: `app/main.py` — `_ALL_PERMISSIONS` list and the RBAC seeding block.

Add:
```python
("tables", "read"),    # list tables with status
("tables", "update"),  # change status (server-level)
```

> `("tables", "manage")` already exists for create/delete; keep it.

Role → permission mapping:

| Role | Permissions |
|---|---|
| `admin` | `tables:manage`, `tables:read`, `tables:update` |
| `server` | `tables:read`, `tables:update` |
| `cashier` | `tables:read` |
| `cook` | `tables:read` |

> The `waiting` transition is open to any authenticated user in the same restaurant —
> enforced inline at the route level, not via a permission entry.

---

### Step 8 — Update & Add Router Endpoints

**File**: `app/routers/restaurant_table.py`

#### 8a. Update existing `GET /tables`

- Change `response_model` to `List[RestaurantTablePublic]`.
- No logic change — the ORM returns the new fields automatically after the migration.

#### 8b. New `PATCH /tables/{table_id}/status`

```
PATCH /tables/{table_id}/status
Body: RestaurantTableStatusUpdate
Auth: any authenticated user (restaurant-scoped check done inline)
Response: RestaurantTablePublic
```

Logic outline:

1. Fetch the table by `table_id`; 404 if not found.
2. Verify `table.restaurant_id == current_user.restaurant_id`; 403 otherwise.
3. Check transition rules (Step 5):
   - `waiting`: no permission needed; any user in same restaurant is allowed.
   - Other transitions: call `permission_service.can(current_user, "tables", "update", db)`;
     raise 403 if denied.
   - `reserved`: additionally validate all three reservation fields are present.
   - `assigned` guard: if caller is a `server` role and table is currently `assigned`,
     require `current_user.id == table.server_id`.
4. Snapshot `old_status = table.status`.
5. Apply field changes per Step 5 rules.
6. Set `table.updated_at = datetime.now()`.
7. `session.add(table)`, `session.commit()`, `session.refresh(table)`.
8. Insert `TableStatusLog(table_id, changed_by_id=current_user.id, old_status, new_status)`.
9. `session.add(log)`, `session.commit()`.
10. Enqueue WebSocket broadcast via `background_tasks.add_task(...)` (see Step 9).
11. Return updated table.

#### 8c. New `GET /tables/{table_id}/logs`

```
GET /tables/{table_id}/logs
Auth: tables:read permission
Response: List[TableStatusLogPublic]
```

Logic outline:

1. Fetch the table; 404 if not found.
2. Verify `table.restaurant_id == current_user.restaurant_id`; 403 otherwise.
3. Query `TableStatusLog` where `table_id == table_id`, ordered by `changed_at DESC`.
4. Return the list.

---

### Step 9 — WebSocket Broadcast for Table Status Changes

**Pattern**: reuse the existing `ConnectionManager` singleton and `broadcast_to_restaurant`
method, the same way the orders router uses `background_tasks.add_task`.

The `PATCH /tables/{table_id}/status` endpoint (and the auto-release trigger in Step 10)
should accept `BackgroundTasks` and `ConnectionManager` as dependencies and enqueue:

```python
background_tasks.add_task(
    manager.broadcast_to_restaurant,
    str(current_user.restaurant_id),
    {
        "type": "table_status_changed",
        "table_id": table.id,
        "table_name": table.name,
        "old_status": old_status,
        "new_status": table.status,
        "server_id": table.server_id,
        "waiting_since": table.waiting_since.isoformat() if table.waiting_since else None,
        "reservation_at": table.reservation_at.isoformat() if table.reservation_at else None,
        "changed_by_id": current_user.id,
        "timestamp": datetime.now().isoformat(),
    }
)
```

> The `restaurant_id` key in `active_connections` is stored as a string (see `ws_service.py`
> line 22 — `restaurant_id` comes in as a path string). Cast with `str(...)` to match.

No changes to `ws_service.py` or `ws_connect.py` are needed.

---

### Step 10 — Auto-Release Table When All Orders Are Paid

**File**: `app/routers/orders.py` (the `PATCH /orders/{order_id}` endpoint)

After an order update is committed, add a check:

1. Load all orders for `order_db.restaurant_table_id`.
2. If every order for that table has `payment_status == PaymentStatus.PAID` (or
   `order_status == OrderStatus.CANCELLED`), automatically set the table status to `free`.
3. Clear `server_id`, `waiting_since`, and all reservation fields.
4. Insert a `TableStatusLog` row with `changed_by_id = None` and
   `note = "auto-released: all orders paid"`.
5. Commit the table change.
6. Enqueue a WebSocket broadcast with `type: "table_status_changed"` and
   `changed_by_id: null` so clients know the release was automatic.

> This logic should be extracted into a helper function (e.g.,
> `maybe_auto_release_table(table_id, session, background_tasks, manager)`) and called from
> the orders router to keep the endpoint readable.

---

### Step 11 — Register Router Updates in `main.py`

The `restaurant_table` router is already registered. No new router file is needed.
Confirm the prefix in `app/main.py` is consistent with the existing table endpoints.

---

## File Change Summary

| File | Change |
|---|---|
| `app/schemas/restaurant_table_schemas.py` | Add `TableStatus` enum; update `RestaurantTableBase` and `RestaurantTablePublic`; add `RestaurantTableStatusUpdate` and `TableStatusLogPublic` |
| `app/models/models.py` | Add 6 new fields to `RestaurantTableBase`; add `server` and `status_logs` relationships on `RestaurantTable`; add `assigned_tables` reverse on `User`; add new `TableStatusLog` model |
| `alembic/versions/<ts>_add_table_status_reservation_and_log.py` | Migration: 6 new columns on `restaurant_table`, new `table_status_log` table |
| `app/main.py` | Add `tables:read` and `tables:update` permissions; update role→permission seeding |
| `app/routers/restaurant_table.py` | Update `GET /tables` response model; add `PATCH /tables/{id}/status`; add `GET /tables/{id}/logs` |
| `app/routers/orders.py` | Add auto-release check after payment update; extract `maybe_auto_release_table` helper |
