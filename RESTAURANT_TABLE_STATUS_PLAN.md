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
| `seats` | `Optional[int]` | Number of seats at the table; informational only |

> Reservation details are **not** stored on the table itself — they live in the
> separate `TableReservation` model below. This supports reservation history,
> booking reservations in advance while a table is still occupied, and future
> fields like party size or duration.

---

## New Model: `Reservation`

Holds the contact details and lifecycle status for a single booking. One reservation
can span **multiple tables** (e.g. a large party split across two tables).

| Field | Type | Notes |
|---|---|---|
| `id` | `int` PK | Auto-increment |
| `name` | `str` | Contact name for the reservation |
| `phone` | `str` | Contact phone for the reservation |
| `reserved_at` | `datetime` | Date and time of the planned arrival |
| `status` | `ReservationStatus` enum | `active`, `honored`, `cancelled`, `no_show` |
| `created_by_id` | `Optional[int]` FK → `user.id` | Who created the reservation |
| `note` | `Optional[str]` | Free-text note for the reservation (e.g. special requests) |
| `created_at` | `datetime` | `default_factory=datetime.now` |
| `updated_at` | `datetime` | `default_factory=datetime.now` |

> There is no explicit "honored at" or "cancelled at" timestamp on `Reservation`.
> That timing is implicitly preserved by `TableStatusLog`: the `changed_at` of the
> log row where `new_status` leaves `reserved` tells you exactly when the reservation
> was acted on for each table. The full timeline (reserved → waiting → assigned) is
> reconstructable from the log without any extra fields here.

---

## New Model: `TableReservation`

Join table linking a `Reservation` to each `RestaurantTable` it covers.
A table's `reserved` status means at least one active `TableReservation` row exists
pointing to an active `Reservation`. Transitioning a table away from `reserved`
marks its `TableReservation` rows `honored` (for `waiting`/`assigned`) or
`cancelled` (for `free`); if all tables in the reservation have left `reserved`,
the parent `Reservation` is updated to the same terminal status.

| Field | Type | Notes |
|---|---|---|
| `id` | `int` PK | Auto-increment |
| `reservation_id` | `int` FK → `reservation.id` | The parent reservation |
| `table_id` | `int` FK → `restaurant_table.id` | The table being reserved |
| `status` | `ReservationStatus` enum | Per-table status; `active`, `honored`, `cancelled`, `no_show` |
| `created_at` | `datetime` | `default_factory=datetime.now` |
| `updated_at` | `datetime` | `default_factory=datetime.now` |

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

### Step 1 — Define the `TableStatus` and `ReservationStatus` Enums ✅

**File**: `app/schemas/restaurant_table_schemas.py`

Add both string enums following the same pattern as `OrderStatus`:

```python
class TableStatus(str, Enum):
    FREE     = "free"
    RESERVED = "reserved"
    WAITING  = "waiting"
    ASSIGNED = "assigned"


class ReservationStatus(str, Enum):
    ACTIVE    = "active"
    HONORED   = "honored"
    CANCELLED = "cancelled"
    NO_SHOW   = "no_show"
```

---

### Step 2 — Update `RestaurantTableBase` and `RestaurantTable` ✅

**File**: `app/models/models.py`

1. In `RestaurantTableBase` add four new fields with safe defaults:
   - `status: TableStatus = TableStatus.FREE`
   - `server_id: Optional[int] = Field(default=None, foreign_key="user.id")`
   - `waiting_since: Optional[datetime] = Field(default=None)`
   - `seats: Optional[int] = Field(default=None)`

2. In `RestaurantTable` (the `table=True` class) add:
   - `server: Optional[User] = Relationship(back_populates="assigned_tables")`
   - `status_logs: List["TableStatusLog"] = Relationship(back_populates="table")`
   - `table_reservations: List["TableReservation"] = Relationship(back_populates="table")`

3. On the `User` model add the reverse side:
   - `assigned_tables: List["RestaurantTable"] = Relationship(back_populates="server")`

> `server_id` references `user.id` — servers are users with the `server` role.

---

### Step 3 — Add the `Reservation`, `TableReservation`, and `TableStatusLog` Models ✅

**File**: `app/models/models.py`

Add all three SQLModel table classes **after** `RestaurantTable`:

```python
class Reservation(SQLModel, table=True):
    __tablename__ = "reservation"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    phone: str
    reserved_at: datetime
    status: ReservationStatus = ReservationStatus.ACTIVE
    note: Optional[str] = Field(default=None)
    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    table_reservations: List["TableReservation"] = Relationship(back_populates="reservation")
    created_by: Optional[User] = Relationship()


class TableReservation(SQLModel, table=True):
    __tablename__ = "table_reservation"

    id: Optional[int] = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id")
    table_id: int = Field(foreign_key="restaurant_table.id")
    status: ReservationStatus = ReservationStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    reservation: Reservation = Relationship(back_populates="table_reservations")
    table: RestaurantTable = Relationship(back_populates="table_reservations")


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

### Step 4 — Update Schemas ✅

**File**: `app/schemas/restaurant_table_schemas.py`

1. **`RestaurantTableBase`** — add the four new fields (same defaults as the model), including `seats: Optional[int] = None`.

2. **`RestaurantTablePublic`** — extend to expose the new fields plus:
   - a nested server object `{ id, username }` so clients don't need a second request,
   - the currently-active reservation (if any) as a nested
     `active_reservation: Optional[TableReservationPublic]`.

3. **`RestaurantTableStatusUpdate`** — narrow schema accepted by the status-change
   endpoint. When `status == "reserved"` the caller may either supply an existing
   `reservation_id` (to attach this table to an already-created reservation) **or**
   supply inline contact fields to create a new one:

   ```python
   class RestaurantTableStatusUpdate(SQLModel):
       status: TableStatus
       reservation_id: Optional[int] = None        # attach to existing reservation
       reservation_name: Optional[str] = None      # \
       reservation_phone: Optional[str] = None     #  } create new reservation
       reservation_at: Optional[datetime] = None   # /
       reservation_note: Optional[str] = None      # optional note (new reservation only)
   ```

   Validate in the router: when `status == "reserved"`, exactly one of
   (`reservation_id`) or (all three inline fields) must be provided; return HTTP 422
   otherwise. The router creates/reuses a `Reservation` row and then creates a
   `TableReservation` link — it does **not** write contact info onto the table itself.

4. **`ReservationPublic`** — response schema for the parent reservation:

   ```python
   class ReservationPublic(SQLModel):
       id: int
       name: str
       phone: str
       reserved_at: datetime
       status: ReservationStatus
       note: Optional[str]
       created_by_id: Optional[int]
       created_at: datetime
       updated_at: datetime
   ```

5. **`TableReservationPublic`** — response schema for a per-table reservation link:

   ```python
   class TableReservationPublic(SQLModel):
       id: int
       reservation_id: int
       table_id: int
       status: ReservationStatus
       reservation: ReservationPublic
       created_at: datetime
       updated_at: datetime
   ```

   `RestaurantTablePublic.active_reservation` becomes
   `active_reservation: Optional[TableReservationPublic]` (unchanged name, updated type).

6. **`TableStatusLogPublic`** — response schema for the log endpoint:

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

### Step 5 — Business Rules for Status Transitions ✅ (spec only — enforced in Step 8)

Enforced in the router / service layer, **not** in the schema:

| Transition | Who can do it | Side effects |
|---|---|---|
| Any → `waiting` | Any authenticated user in the same restaurant | On table: set `waiting_since = now()`; clear `server_id`. TableReservation: mark any active row `honored`; if all rows for that `Reservation` are now terminal, set `Reservation.status = honored`. |
| Any → `assigned` | `server`, `admin`, `super_admin` | On table: set `server_id = current_user.id`; clear `waiting_since`. TableReservation: same cascade as `waiting`. |
| Any → `free` | `server`, `admin`, `super_admin` | On table: clear `server_id`, `waiting_since`. TableReservation: mark any active row `cancelled`; if all rows for that `Reservation` are now terminal, set `Reservation.status = cancelled`. |
| Any → `reserved` | `admin`, `super_admin` | On table: clear `server_id`, `waiting_since`. Reservation: if `reservation_id` supplied, reuse that row; otherwise create a new `Reservation` with `name`, `phone`, `reserved_at`, `created_by_id = current_user.id`. Either way, insert a `TableReservation` link row with `status=active`. |

**Additional guard**: if the table is currently `assigned` and the caller's role is `server`,
only allow the transition if `current_user.id == table.server_id`. Admins bypass this.

**After every successful transition** (applies to all cases including auto-release):
1. Insert a `TableStatusLog` row with `old_status`, `new_status`, `changed_by_id`, and
   an optional `note`.
2. Broadcast a WebSocket event to the restaurant room (see Step 9).

---

### Step 6 — Alembic Migration ✅

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
        batch_op.add_column(sa.Column("seats", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_restaurant_table_server_id_user",
            "user", ["server_id"], ["id"]
        )

    # New reservation table (parent booking)
    op.create_table(
        "reservation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("reserved_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # New table_reservation table (per-table link)
    op.create_table(
        "table_reservation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reservation_id", sa.Integer(), nullable=False),
        sa.Column("table_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservation.id"]),
        sa.ForeignKeyConstraint(["table_id"], ["restaurant_table.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_table_reservation_table_id_status",
        "table_reservation", ["table_id", "status"]
    )
    op.create_index(
        "ix_table_reservation_reservation_id",
        "table_reservation", ["reservation_id"]
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

    # Index to make the auto-release EXISTS query fast (see Step 10)
    op.create_index(
        "ix_order_restaurant_table_id_payment_status",
        "order", ["restaurant_table_id", "payment_status"]
    )

def downgrade() -> None:
    op.drop_index("ix_order_restaurant_table_id_payment_status", table_name="order")
    op.drop_table("table_status_log")
    op.drop_index("ix_table_reservation_reservation_id", table_name="table_reservation")
    op.drop_index("ix_table_reservation_table_id_status", table_name="table_reservation")
    op.drop_table("table_reservation")
    op.drop_table("reservation")
    with op.batch_alter_table("restaurant_table", schema=None) as batch_op:
        batch_op.drop_constraint("fk_restaurant_table_server_id_user", type_="foreignkey")
        batch_op.drop_column("seats")
        batch_op.drop_column("waiting_since")
        batch_op.drop_column("server_id")
        batch_op.drop_column("status")
```

Run with: `alembic upgrade head`

---

### Step 7 — Add New Permissions ✅ (already present in `_ALL_PERMISSIONS` and role mappings) ✅

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

### Step 8 — Update & Add Router Endpoints ✅ ✅

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
   - `reserved`: validate that either `reservation_id` or all three inline fields are
     provided (but not both); return HTTP 422 otherwise.
   - `assigned` guard: if caller is a `server` role and table is currently `assigned`,
     require `current_user.id == table.server_id`.
4. Snapshot `old_status = table.status`.
5. Apply side effects per Step 5:
   - Update `server_id` / `waiting_since` on the table.
   - Fetch the active `TableReservation` for this table (if any) via
     `SELECT * FROM table_reservation WHERE table_id=:tid AND status='active' LIMIT 1`.
   - If transitioning **away from** `reserved`, mark that row `honored` (for
     `waiting`/`assigned`) or `cancelled` (for `free`), bump `updated_at`; then check
     whether all `TableReservation` rows for the parent `Reservation` are now terminal —
     if so, update `Reservation.status` to match.
   - If transitioning **to** `reserved`:
     - If `reservation_id` supplied: look up that `Reservation`; 404 if not found.
     - Otherwise: create a new `Reservation` with inline fields and
       `created_by_id=current_user.id`.
     - Insert a `TableReservation` link row with `status=active`.
6. Set `table.status = new_status`, `table.updated_at = datetime.now()`.
7. Insert `TableStatusLog(table_id, changed_by_id=current_user.id, old_status, new_status)`.
8. Single `session.commit()` covers table + reservation + log changes atomically;
   then `session.refresh(table)`.
9. Enqueue WebSocket broadcast via `background_tasks.add_task(...)` (see Step 9).
10. Return updated table (includes nested `active_reservation`).

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

### Step 9 — WebSocket Broadcast for Table Status Changes ✅ ✅

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

### Step 10 — Auto-Release Table When All Orders Are Paid ✅ ✅

**File**: `app/routers/orders.py` (the `PATCH /orders/{order_id}` endpoint)

**Strategy**: don't load orders into Python. Issue **one** aggregate SQL query to
check whether any unpaid, non-cancelled orders remain for the table. If the answer
is "no", release the table. This keeps the work to a single indexed round-trip
regardless of how many orders the table has.

After an order update is committed, in a helper
`maybe_auto_release_table(table_id, current_user, session, background_tasks, manager)`:

1. Fetch the table; if already `free`, return early.
2. Run the EXISTS check:

   ```python
   from sqlmodel import select, exists
   from sqlalchemy import and_

   has_open_orders = session.exec(
       select(
           exists().where(
               and_(
                   Order.restaurant_table_id == table_id,
                   Order.payment_status != PaymentStatus.PAID,
                   Order.order_status != OrderStatus.CANCELLED,
               )
           )
       )
   ).one()
   if has_open_orders:
       return
   ```

   The migration in Step 6 adds `ix_order_restaurant_table_id_payment_status` so this
   query stays fast as the orders table grows.
3. Snapshot `old_status = table.status`.
4. Set `table.status = TableStatus.FREE`; clear `server_id` and `waiting_since`.
5. Mark any active `TableReservation` for this table as `cancelled` (bump `updated_at`).
6. Insert `TableStatusLog(table_id, changed_by_id=None, old_status, new_status=free,
   note="auto-released: all orders paid")`.
7. Single `session.commit()`.
8. Enqueue a WebSocket broadcast with `type: "table_status_changed"` and
   `changed_by_id: null` so clients know the release was automatic.

> Call this helper from the `PATCH /orders/{order_id}` handler after its own commit,
> only when the update actually touched `payment_status` or `order_status` — no point
> running the query for unrelated field changes.

> **Mirror behavior — Auto-Claim on order creation.** `POST /orders` runs
> `maybe_auto_claim_table` at the end of `create_order`, moving the table into
> `assigned` or `waiting` depending on the creator's role. Helpers live in
> `app/services/table_status_service.py` alongside `maybe_auto_release_table`.
> See [TABLE_AUTO_CLAIM_PLAN.md](TABLE_AUTO_CLAIM_PLAN.md) for the transition
> matrix and rationale.

---

### Step 11 — Register Router Updates in `main.py` ✅ ✅

The `restaurant_table` router is already registered. No new router file is needed.
Confirm the prefix in `app/main.py` is consistent with the existing table endpoints.

---

## File Change Summary

| File | Change |
|---|---|
| `app/schemas/restaurant_table_schemas.py` | Add `TableStatus` and `ReservationStatus` enums; update `RestaurantTableBase` and `RestaurantTablePublic` (incl. `active_reservation`); add `RestaurantTableStatusUpdate`, `ReservationPublic`, `TableReservationPublic`, `TableStatusLogPublic` |
| `app/models/models.py` | Add 4 new fields to `RestaurantTableBase`; add `server`, `status_logs`, `table_reservations` relationships on `RestaurantTable`; add `assigned_tables` reverse on `User`; add new `Reservation`, `TableReservation`, and `TableStatusLog` models |
| `alembic/versions/<ts>_add_table_status_reservation_and_log.py` | Migration: 4 new columns on `restaurant_table`, new `reservation`, `table_reservation`, and `table_status_log` tables, indexes on reservations and `order` for the auto-release EXISTS query |
| `app/main.py` | Add `tables:read` and `tables:update` permissions; update role→permission seeding |
| `app/routers/restaurant_table.py` | Update `GET /tables` response model; add `PATCH /tables/{id}/status` (creates/updates `TableReservation` rows); add `GET /tables/{id}/logs` |
| `app/routers/orders.py` | Add `maybe_auto_release_table` helper using a single EXISTS query; call it after payment/status updates |
