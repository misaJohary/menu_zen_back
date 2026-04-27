# Auto-Release Fix & Daily Table Reset — Implementation Plan

## Context

Two related problems need to be solved:

1. **Bug: tables are not auto-released** when all of their orders are marked paid, even though `maybe_auto_release_table` is wired into the order update endpoints (see [app/services/table_status_service.py](app/services/table_status_service.py#L189) and the three call-sites in [app/routers/orders.py](app/routers/orders.py)).
2. **Missing feature: a "start-of-day" reset** so all tables in a restaurant start the day as `free`, leftover reservations are closed, and stale orders from the previous service don't leak into today.

Both problems share a root cause (stale orders from prior services linger on tables), so the fixes are designed together.

---

## Part 1 — Why Auto-Release Is Not Firing

Below is a ranked list of root causes, from most to least likely. The fix plan in Part 3 addresses all three.

### Cause A (most likely) — Stale open orders from previous days block the EXISTS check

The helper filters only by `restaurant_table_id`, with no date or "current session" bound:

```python
# app/services/table_status_service.py:204-214
has_open_orders = session.exec(
    select(
        exists().where(
            sa_and(
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

Any past order where `payment_status` stayed `unpaid` (walkouts, servers that forgot to close a tab, test data, orders cancelled from the POS but left as `unpaid` instead of `cancelled`, etc.) permanently prevents the table from ever auto-releasing. Once even one "ghost" order exists on a table, this branch always takes the `return` and the table stays `assigned`/`waiting` forever.

This matches the symptom the user is observing: *"the table is not even released"* despite the current order being marked paid.

### Cause B — `PATCH /orders/{order_id}/payment` signature bug

```python
# app/routers/orders.py:239-246
@router.patch("/orders/{order_id}/payment", ...)
def change_order_payment(
    order_id: int,
    session: SessionDep,
    payment_status: PaymentStatus,     # ← no Body() / no Query()
    background_tasks: BackgroundTasks,
    manager: ConnectionManager = Depends(get_connection_manager),
):
```

Because `PaymentStatus` is an `Enum` (a simple type), FastAPI infers it as a **query parameter**, not a body. If the frontend posts `{"status": "paid"}` in the request body, FastAPI returns 422 and `order_db.payment_status` is never updated, so of course auto-release never triggers.

This endpoint also has no `current_user` dependency, which is inconsistent with the rest of the router and blocks any future restaurant-scoped guard.

### Cause C — `PATCH /orders/{order_id}` silently re-writes `payment_status` to its default

```python
# app/schemas/order_shemas.py
class OrderBase(SQLModel):
    ...
    payment_status: PaymentStatus = PaymentStatus.UNPAID

class OrderUpdate(OrderBase):
    payment_status: Optional[PaymentStatus] = Field(default=None)
    ...
```

`OrderUpdate` overrides `payment_status` with `Optional[...] = None`, so `exclude_unset=True` works correctly **only if the frontend omits the field**. If the frontend ever sends `payment_status: null` or re-posts the whole order object with `payment_status: "unpaid"`, `sqlmodel_update` quietly overwrites a previously-paid order back to `unpaid` — and then auto-release (correctly) refuses to fire.

Worth ruling out with a single SQL check on the affected tables — see the diagnostic step in Part 3.

---

## Part 2 — Why "Morning Reset" Is the Natural Partner Fix

Even after fixing A/B/C, the restaurant still accumulates `unpaid` orders over weeks: no-shows, scoped-out tabs, data-entry mistakes. Without a daily boundary, these accumulate indefinitely and will eventually re-break auto-release on some tables.

A daily reset:
- Sets every table back to `free`.
- Closes hanging reservations (active ones whose planned arrival already passed become `no_show`; future ones stay active).
- **Closes stale orders** so they can no longer block future auto-release on the same table.
- Emits a `TableStatusLog` entry per affected table (`note="daily reset"`) and one broadcast so connected clients refresh.

This gives the system a clean "service boundary" each morning and makes auto-release self-healing.

---

## Part 3 — Proposed Solution

### Step 1 — Add a diagnostic before changing anything

Before deploying the code change, run this read-only SQL to confirm Cause A on the live DB:

```sql
-- Tables that are currently non-free and have >=1 non-paid, non-cancelled order
-- older than 24h. If this returns rows, Cause A is the culprit.
SELECT rt.id, rt.name, rt.status,
       COUNT(o.id) AS stale_open_orders,
       MIN(o.created_at) AS oldest_open
FROM restaurant_table rt
JOIN "order" o ON o.restaurant_table_id = rt.id
WHERE rt.status != 'free'
  AND o.payment_status != 'paid'
  AND o.order_status   != 'cancelled'
  AND o.created_at < datetime('now', '-1 day')
GROUP BY rt.id;
```

Expected: one row per "stuck" table. Record the output — it becomes the input for the one-time cleanup in Step 5.

### Step 2 — Fix `PATCH /orders/{order_id}/payment` (Cause B)

**File**: [app/routers/orders.py](app/routers/orders.py#L239-L260)

1. Introduce a body schema `OrderPaymentUpdate` (it already exists at line 235 but is unused — wire it in):
   ```python
   class OrderPaymentUpdate(SQLModel):
       status: PaymentStatus
   ```
2. Change the signature so the payload is read from the JSON body, and add a `current_user` dependency to match the other endpoints:
   ```python
   def change_order_payment(
       order_id: int,
       payload: OrderPaymentUpdate,
       session: SessionDep,
       background_tasks: BackgroundTasks,
       current_user: Annotated[User, Depends(get_current_active_user)],
       manager: ConnectionManager = Depends(get_connection_manager),
   ):
       ...
       order_db.payment_status = payload.status
   ```
3. Broadcast a `payment_updated` WS event after the commit so clients can refresh, then call `maybe_auto_release_table` (already present).

> If the frontend is already calling this endpoint with a query string, coordinate the switch-over — or temporarily accept both by using `payment_status: PaymentStatus = Body(...)`.

### Step 3 — Make `maybe_auto_release_table` session-scoped (Cause A)

**File**: [app/services/table_status_service.py](app/services/table_status_service.py#L189)

The helper should only consider orders that belong to the **current occupancy**, not every order the table has ever had. Two options:

**Option A (recommended) — use the most recent "entered-non-free" transition as the lower bound.**

Add a helper that returns the `changed_at` of the newest `TableStatusLog` row where `old_status = 'free'` and `new_status != 'free'` for the table. Fall back to `datetime.min` if none exists (shouldn't happen post-migration, but defensive). Then tighten the EXISTS clause:

```python
from sqlalchemy import and_ as sa_and

session_start = _current_occupancy_started_at(session, table_id)  # new helper

has_open_orders = session.exec(
    select(
        exists().where(
            sa_and(
                Order.restaurant_table_id == table_id,
                Order.payment_status != PaymentStatus.PAID,
                Order.order_status   != OrderStatus.CANCELLED,
                Order.created_at     >= session_start,   # ← NEW
            )
        )
    )
).one()
```

Pros: no schema change; uses data we already log; implicitly scoped to each occupancy.
Cons: one extra indexed query per payment update (negligible).

**Option B — add a `current_session_started_at: Optional[datetime]` column on `restaurant_table`.**

Set it when the table leaves `free`, clear it when it returns to `free`. Simpler logic, but costs a migration. Prefer A unless you already plan another migration in the same train.

Either way, add a composite index for the new filter — the plan doc's Step 6 migration already created `ix_order_restaurant_table_id_payment_status`; extend it to `(restaurant_table_id, payment_status, created_at)` if you go with Option A and the query planner doesn't pick up the existing one.

### Step 4 — Tighten `OrderUpdate` to prevent silent overwrites (Cause C)

**File**: [app/schemas/order_shemas.py](app/schemas/order_shemas.py#L43-L49)

`OrderUpdate` is already `Optional[...] = None` for these fields — that's correct. The risk is only if callers post `payment_status: null`. Two cheap hardenings:

1. In `PATCH /orders/{order_id}`, after `order.model_dump(exclude_unset=True, ...)`, drop keys whose value is `None` before calling `sqlmodel_update`. This makes `null` equivalent to "not sent".
2. Add a quick server-side guard: if the incoming `payment_status` would **downgrade** a `paid`/`refunded` order back to `unpaid`/`prepaid`, reject with 422 (or require `payments:override` permission). Rare in practice but cheap to enforce.

### Step 5 — One-time cleanup migration / script

Based on Step 1's diagnostic:

```sql
-- Close out stale "ghost" orders so they stop blocking auto-release.
-- Choose the intent: cancel them, or mark paid-without-payment.
UPDATE "order"
SET order_status = 'cancelled', updated_at = CURRENT_TIMESTAMP
WHERE payment_status != 'paid'
  AND order_status   != 'cancelled'
  AND created_at < datetime('now', '-1 day');
```

Then a sweep that releases any table whose open-order count is now zero — reuse the daily-reset endpoint from Step 6 with a flag, or run it as a one-off Alembic data migration. Insert a `TableStatusLog` entry per table with `note="cleanup: stale orders closed"` for auditability.

> Run this in a transaction off-hours and review the diff before committing. Never run from the API surface.

---

## Part 4 — Daily Reset Feature

### Step 6 — New endpoint: `POST /tables/reset-daily`

**File**: [app/routers/restaurant_table.py](app/routers/restaurant_table.py)

```
POST /tables/reset-daily
Auth: admin or super_admin  (new permission: ("tables", "reset"))
Body: ResetDailyRequest (optional fields — see below)
Response: ResetDailySummary
```

#### Request schema

```python
class ResetDailyRequest(SQLModel):
    # If omitted, defaults to True. Closes unpaid, non-cancelled orders created
    # before today so they can't block tomorrow's auto-release logic.
    close_stale_orders: bool = True
    # If omitted, defaults to True. Marks any active TableReservation whose
    # parent Reservation.reserved_at is in the past as `no_show`; leaves
    # future reservations untouched so tomorrow's bookings survive the reset.
    expire_past_reservations: bool = True
    # Optional override — by default the reset's "today" boundary is
    # `datetime.now()`. Supply a cutoff to replay a reset for a specific date.
    cutoff: Optional[datetime] = None
```

#### Response schema

```python
class ResetDailySummary(SQLModel):
    restaurant_id: int
    tables_reset: int           # how many transitioned to `free`
    tables_already_free: int
    reservations_expired: int   # TableReservation rows flipped to no_show
    orders_closed: int          # Orders flipped to cancelled
    reset_at: datetime
```

#### Handler logic (one transaction)

1. Verify `current_user.restaurant_id` is set; load `cutoff = payload.cutoff or datetime.now()`.
2. Require `tables:reset` permission (see Step 7).
3. Fetch all `RestaurantTable` rows for the restaurant.
4. **Expire past reservations** (if flag true):
   - `UPDATE table_reservation SET status='no_show' WHERE status='active' AND table_id IN (this restaurant's tables) AND EXISTS (SELECT 1 FROM reservation r WHERE r.id = table_reservation.reservation_id AND r.reserved_at < :cutoff)`.
   - Then run `cascade_parent_reservation_status` for each affected `Reservation` so the parent row's status matches.
5. **Close stale orders** (if flag true):
   - `UPDATE "order" SET order_status='cancelled' WHERE restaurant_table_id IN (...) AND payment_status != 'paid' AND order_status != 'cancelled' AND created_at < :cutoff`.
   - Capture the count for the response summary.
6. **Reset tables**: for each non-free table, in a single loop:
   - Snapshot `old_status`.
   - Set `status=free`, `server_id=None`, `waiting_since=None`, `updated_at=now()`.
   - Any still-active `TableReservation` rows on this table whose parent is in the past got handled in step 4; any remaining active rows (future bookings) stay untouched — **important**: a reservation for *tonight* must survive a morning reset.
   - Insert `TableStatusLog(table_id, changed_by_id=current_user.id, old_status, new_status=free, note="daily reset")`.
7. Single `session.commit()` for the whole operation. If it fails, nothing changes — this is the right blast-radius behavior for a batch endpoint.
8. **After commit**, enqueue WebSocket broadcasts:
   - One per reset table with `type="table_status_changed"`, `changed_by_id=current_user.id`, and the usual payload — so clients that listen per-table update correctly.
   - Plus one summary event `type="daily_reset"` with the full summary object, so dashboards can show a toast.
   - Use `background_tasks.add_task` — do not block the HTTP response.
9. Return `ResetDailySummary`.

> Call the helpers from [app/services/table_status_service.py](app/services/table_status_service.py) (`active_table_reservation`, `cascade_parent_reservation_status`, `build_status_broadcast`) to keep the logic consistent with the rest of the status machinery — do not reimplement locally.

### Step 7 — Add `("tables", "reset")` permission

**File**: [app/main.py](app/main.py#L46)

1. Append `("tables", "reset")` to `_ALL_PERMISSIONS`.
2. Add it to the `admin` and `super_admin` role seed lists. Do **not** grant it to `server`, `cashier`, or `cook`.
3. Use `require_permission("tables", "reset")` on the endpoint.

### Step 8 — Manual endpoint today, scheduled job tomorrow (optional)

The user asked for a manual endpoint, so ship Step 6 first. Once it's proven in production, layer on an automatic trigger without changing the endpoint's contract:

- **Option 1 — APScheduler**: add a per-restaurant `reset_hour: Optional[int]` column on `restaurant`, and a single background job that wakes every hour, finds restaurants whose local-time hour matches, and calls the same service function the endpoint calls. Timezone handling is the only subtle bit — store the restaurant's IANA timezone string.
- **Option 2 — Cron / external trigger**: leave the endpoint as the one source of truth and have an external scheduler (cron on the host, a CI action, or the existing `/loop` facility) `POST` to it each morning with service-account credentials.

Option 2 is strictly easier and requires zero new code — recommended unless multi-tenant timezone support lands soon.

### Step 9 — Audit / history considerations

Every table reset goes through `TableStatusLog` with `note="daily reset"` and `changed_by_id=current_user.id`, so the existing `GET /tables/{id}/logs` endpoint already surfaces the history — no new reporting endpoint needed.

For the closed orders, consider a lightweight `OrderAuditLog` table if business cares who closed what on which reset. Out of scope for the first pass; rely on `order.updated_at` plus the reset timestamp for correlation for now.

---

## File Change Summary

| File | Change |
|---|---|
| `app/services/table_status_service.py` | Add `_current_occupancy_started_at` helper; tighten `maybe_auto_release_table` EXISTS query to filter by `Order.created_at >= session_start` |
| `app/routers/orders.py` | Fix `PATCH /orders/{order_id}/payment`: take `OrderPaymentUpdate` body schema and add `current_user` dependency; harden `PATCH /orders/{order_id}` against `null` overwrites of `payment_status` / `order_status` |
| `app/routers/restaurant_table.py` | Add `POST /tables/reset-daily` endpoint; add `ResetDailyRequest` / `ResetDailySummary` schemas |
| `app/schemas/restaurant_table_schemas.py` | Add `ResetDailyRequest` and `ResetDailySummary` |
| `app/main.py` | Add `("tables", "reset")` to `_ALL_PERMISSIONS` and to the `admin`/`super_admin` role seeds |
| `alembic/versions/<ts>_close_stale_orders.py` *(optional)* | One-time data migration to close orders matching the stale-order criteria and log `TableStatusLog` cleanup entries; alternative to running the SQL from Step 5 by hand |

---

## Rollout Order

1. **Diagnostic SQL** from Step 1 — confirms Cause A on production data.
2. **Ship Step 3** (session-scoped EXISTS) — this alone unblocks auto-release going forward without touching any existing data.
3. **Ship Steps 2 and 4** — fixes the payment endpoint contract and hardens the update schema.
4. **Run Step 5 cleanup** out of hours so already-stuck tables release.
5. **Ship Steps 6–7** — manual daily reset endpoint; have the admin click it the next morning to verify.
6. **Decide on Step 8** scheduling after a week of manual use.
