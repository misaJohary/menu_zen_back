# Table Auto-Claim on Order Creation — Implementation Plan

## Overview

Today the system already **auto-releases** a table (→ `free`) once all its orders are
paid via `maybe_auto_release_table` in `app/routers/orders.py`. The opposite direction —
**claiming** a table when the first order is created — is still manual: the frontend
has to call `PATCH /tables/{id}/status` as a second step after `POST /orders`.

This plan introduces a symmetric helper `maybe_auto_claim_table` that runs at the end
of `POST /orders` and moves the table into the right status (`assigned` or `waiting`)
depending on the caller's role and the current state. It mirrors
`maybe_auto_release_table` in structure, logging, and WebSocket behavior.

---

## Goals

- One API call (`POST /orders`) handles both the order and the table status transition.
- No behavior change for tables already in the correct state (no log spam / no broadcast).
- Existing manual endpoint `PATCH /tables/{id}/status` remains the authoritative path
  for reservations, overrides, and admin reassignments.
- Shared helpers (`_active_table_reservation`, `_cascade_parent_reservation_status`,
  `_build_status_broadcast`) get extracted so both `orders.py` and `restaurant_table.py`
  can call them without cross-importing private names.

---

## Transition Matrix

What `maybe_auto_claim_table` does based on the **current table status** and the
**role of the order creator**:

| Current status | Creator role                        | Target status | Side effects                                                                 |
|----------------|-------------------------------------|---------------|------------------------------------------------------------------------------|
| `free`         | `server` / `admin` / `super_admin`  | `assigned`    | `server_id = creator.id`, `waiting_since = None`                             |
| `free`         | other (`cashier`, `cook`, …)        | `waiting`     | `waiting_since = now()`, `server_id = None`                                  |
| `reserved`     | `server` / `admin` / `super_admin`  | `assigned`    | Same as above + cascade active `TableReservation` → `honored`                |
| `reserved`     | other                                | `waiting`     | `waiting_since = now()` + cascade active `TableReservation` → `honored`      |
| `waiting`      | `server` / `admin` / `super_admin`  | `assigned`    | `server_id = creator.id`, clear `waiting_since`                              |
| `waiting`      | other                                | **no-op**     | (already waiting, no server yet — nothing to do)                             |
| `assigned`     | same `server_id` as creator          | **no-op**     | (additional orders on the same table)                                        |
| `assigned`     | different server                     | **no-op**     | Don't steal ownership — use manual `PATCH /tables/{id}/status` to reassign   |
| `assigned`     | `admin` / `super_admin`              | **no-op**     | Admins adding corrective orders don't reassign the table                     |

**On every non-no-op transition:**
1. Insert a `TableStatusLog` row with `note="auto-claimed: order created"`.
2. Broadcast a `table_status_changed` WebSocket event to the restaurant room.

---

## Step-by-Step Implementation

### Step 1 — Extract Shared Helpers to a Service Module ⬜

**Why first:** `maybe_auto_claim_table` needs `_active_table_reservation`,
`_cascade_parent_reservation_status`, and `_build_status_broadcast`. These currently
live as module-private in `app/routers/restaurant_table.py`. Cross-importing
underscore-prefixed names from another router is a code smell — extract them once.

**Create** `app/services/table_status_service.py` and move:

- `_TERMINAL_RESERVATION_STATUSES` → `TERMINAL_RESERVATION_STATUSES` (public)
- `_active_table_reservation` → `active_table_reservation`
- `_cascade_parent_reservation_status` → `cascade_parent_reservation_status`
- `_build_status_broadcast` → `build_status_broadcast`
- `maybe_auto_release_table` (currently in `orders.py`) → also move here for symmetry

**Update imports** in:
- `app/routers/restaurant_table.py` — replace local helpers with imports from the service.
- `app/routers/orders.py` — import `maybe_auto_release_table` from the service.

- [ ] Create `app/services/table_status_service.py`
- [ ] Move the four helpers + `maybe_auto_release_table`
- [ ] Update `app/routers/restaurant_table.py` imports and call sites
- [ ] Update `app/routers/orders.py` imports and call sites
- [ ] Run the app and hit `GET /tables`, `PATCH /tables/{id}/status`, `PATCH /orders/{id}/payment` to confirm nothing regressed

---

### Step 2 — Add a Role-Classification Helper ⬜

**File:** `app/services/table_status_service.py`

Add a small helper used by the claim logic to decide "server-like" vs "other":

```python
from app.schemas.auth_schemas import RoleName

_SERVER_LIKE_ROLES = {
    RoleName.SERVER.value,
    RoleName.ADMIN.value,
    RoleName.SUPER_ADMIN.value,
}

def is_server_like(role_name: str) -> bool:
    return role_name in _SERVER_LIKE_ROLES
```

- [ ] Add `_SERVER_LIKE_ROLES` constant
- [ ] Add `is_server_like` function
- [ ] Confirm `RoleName` enum values line up with seeded role names in `app/main.py`

---

### Step 3 — Implement `maybe_auto_claim_table` ⬜

**File:** `app/services/table_status_service.py`

**Signature:**

```python
def maybe_auto_claim_table(
    table_id: int,
    current_user: User,
    session: Session,
    background_tasks: BackgroundTasks,
    manager: ConnectionManager,
) -> None
```

**Logic outline:**

1. `table = session.get(RestaurantTable, table_id)` — return if `None`.
2. Defensive: return if `table.restaurant_id != current_user.restaurant_id`.
3. Load role via `permission_service._load_role_name(current_user, session)` — or
   promote `_load_role_name` to public while you're here.
4. Decide target status using the transition matrix above. If the decision is
   **no-op**, return immediately (no log, no broadcast).
5. `old_status = table.status`.
6. If `old_status == RESERVED`:
   - `active = active_table_reservation(session, table.id)`
   - If `active`: mark it `HONORED`, bump `updated_at`, `session.add(active)`,
     capture `parent_reservation_id = active.reservation_id`.
7. Apply table side effects per the target status:
   - `ASSIGNED`: `table.server_id = current_user.id`; `table.waiting_since = None`.
   - `WAITING`:  `table.waiting_since = datetime.now()`; `table.server_id = None`.
8. `table.status = target`; `table.updated_at = datetime.now()`; `session.add(table)`.
9. Insert:
   ```python
   TableStatusLog(
       table_id=table.id,
       changed_by_id=current_user.id,
       old_status=old_status,
       new_status=target,
       note="auto-claimed: order created",
   )
   ```
10. If `parent_reservation_id` is set, call `cascade_parent_reservation_status(...)`.
11. `session.commit()`; `session.refresh(table)`.
12. Re-fetch the active reservation (may now be terminal) and build the broadcast via
    `build_status_broadcast(table, old_status, current_user.id, refreshed_active)`.
13. `background_tasks.add_task(manager.broadcast_to_restaurant, str(table.restaurant_id), payload)`.

**Invariants:**
- Single `session.commit()` covers table + log + reservation cascade atomically.
- No-ops must **not** write a log row or broadcast.
- Never reassign an already-assigned table implicitly.

- [ ] Implement the function per outline
- [ ] Unit-test each row of the transition matrix (or manual test per Step 6)
- [ ] Confirm `session.commit()` happens exactly once and only on real transitions

---

### Step 4 — Wire It Into `POST /orders` ⬜

**File:** `app/routers/orders.py`

Add the call at the end of `create_order`, **after** the final `session.commit()` +
`session.refresh(db_order)` and **before** the WebSocket `new_order` broadcast (so
clients receive the table update first — or after, both are acceptable; pick one
and stay consistent).

```python
if db_order.restaurant_table_id is not None:
    maybe_auto_claim_table(
        db_order.restaurant_table_id,
        current_user,
        session,
        background_tasks,
        manager,
    )
```

- [ ] Import `maybe_auto_claim_table` from `app.services.table_status_service`
- [ ] Add the call after order commit, guarded on `restaurant_table_id is not None`
- [ ] Verify `create_order` still returns the order payload unchanged

---

### Step 5 — (Optional) Expose `_load_role_name` Publicly ⬜

If Step 3 ends up calling `permission_service._load_role_name`, prefer to rename the
function to `load_role_name` (no underscore). Keeping multiple router modules
depending on a private helper is a maintenance hazard.

- [ ] Rename `_load_role_name` → `load_role_name` in `app/services/permission_service.py`
- [ ] Update all call sites (`orders.py`, `restaurant_table.py`, `table_status_service.py`)

> Skip this step if you'd rather not churn callers — referencing the private name
> from the new service is tolerable short-term.

---

### Step 6 — Manual Testing Checklist ⬜

Run through each scenario end-to-end against a dev database. For each, check:
- Table status transitions as expected.
- `TableStatusLog` row exists (or doesn't, for no-ops) with the right `old_status`,
  `new_status`, `changed_by_id`, and `note`.
- WebSocket broadcast fires (or doesn't) with the correct payload.
- `TableReservation` status cascades correctly when leaving `reserved`.

**Scenarios:**

- [ ] **S1**: `free` + server creates order → `assigned`, log written, broadcast sent
- [ ] **S2**: `reserved` + server creates order → `assigned`, active `TableReservation` → `honored`, parent `Reservation` cascaded if applicable
- [ ] **S3**: `free` + cashier creates order → `waiting`, `waiting_since` set, `server_id` stays null
- [ ] **S4**: `assigned` (same server) + same server creates 2nd order → no-op (no log, no broadcast)
- [ ] **S5**: `assigned` to Alice + admin creates order → no-op, `server_id` still Alice
- [ ] **S6**: `assigned` to Alice + server Ben creates order → no-op, table still Alice's
- [ ] **S7**: Full round-trip: `free` → claim → `assigned` → pay all orders → auto-release → `free`. Confirm exactly 2 log rows (one claim, one release).
- [ ] **S8**: `waiting` + server creates order → `assigned`, `waiting_since` cleared
- [ ] **S9**: Order with `restaurant_table_id = None` (if supported) → helper is skipped, no table state touched

---

### Step 7 — Regression Check on Existing Flows ⬜

The refactor in Step 1 moves code; make sure nothing downstream broke.

- [ ] `PATCH /tables/{id}/status` still works for all four target statuses (`free`, `reserved`, `waiting`, `assigned`)
- [ ] `GET /tables/{id}/logs` still returns the right log rows in `changed_at DESC` order
- [ ] `PATCH /orders/{id}/payment` still triggers `maybe_auto_release_table`
- [ ] `PATCH /orders/{id}` and `PATCH /orders/{id}/status` still trigger auto-release when `status_fields_changed`
- [ ] WebSocket clients subscribed to the restaurant room still receive both `table_status_changed` and `new_order` events after a fresh order

---

### Step 8 — Document the Behavior ⬜

- [ ] Update `RESTAURANT_TABLE_STATUS_PLAN.md` — add a short section under Step 10
      ("Auto-Release") noting that the mirror "Auto-Claim" now also exists and
      pointing to this file.
- [ ] Add a one-liner to the README (if one exists) about the implicit
      claim/release behavior so frontend devs know not to call
      `PATCH /tables/{id}/status` after `POST /orders`.
- [ ] Notify the frontend team that the explicit post-order status PATCH is no
      longer needed (but still works if they leave it in temporarily).

---

## File Change Summary

| File                                         | Change                                                                                          |
|----------------------------------------------|-------------------------------------------------------------------------------------------------|
| `app/services/table_status_service.py`       | **New.** Houses shared helpers + `maybe_auto_release_table` + `maybe_auto_claim_table`          |
| `app/routers/restaurant_table.py`            | Drop local helpers, import from the service                                                     |
| `app/routers/orders.py`                      | Drop local `maybe_auto_release_table`, import from the service; call `maybe_auto_claim_table` in `create_order` |
| `app/services/permission_service.py`         | *(Optional)* rename `_load_role_name` → `load_role_name`                                        |
| `RESTAURANT_TABLE_STATUS_PLAN.md`            | Cross-reference this plan                                                                       |

---

## Non-Goals

- **No schema/migration changes.** All existing tables, columns, and enums cover this.
- **No new endpoints.** This is a side-effect wired into the existing `POST /orders`.
- **No removal of `PATCH /tables/{id}/status`.** It remains the canonical path for
  reservations, manual overrides, and admin reassignments.
- **No changes to auto-release logic.** This plan is purely additive on the claim side.

---

## Risks & Open Questions

1. **Steal-on-last-write policy.** The matrix says "server B creates order on server A's
   table → no-op." Some restaurants may want the opposite (last server wins). Confirm
   with the product owner before implementing; if they want steal-on-last-write, the
   `assigned + different server` row of the matrix changes to `→ assigned, server_id = creator.id`.
2. **Order creation failure after claim.** Currently not possible — `create_order`
   commits the order before we call the helper, so a claim failure doesn't roll back
   the order. This matches `maybe_auto_release_table`'s behavior.
3. **Multi-table parties.** If a `Reservation` covers two tables and only one gets an
   order, only that table's `TableReservation` becomes `honored`. The parent stays
   `active` until the second table also transitions. The existing cascade helper
   already handles this correctly.
4. **Race between claim and manual PATCH.** If a server manually sets `reserved` at the
   same moment another creates an order, the last commit wins. Acceptable for this
   workload; revisit if it becomes a practical issue.
