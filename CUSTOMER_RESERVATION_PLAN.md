# Customer Reservation Plan (revised — request-and-approve model)

Feature: authenticated customers send a reservation **request** to a restaurant. The backend stores it as `waiting`, emails the restaurant owner, and exposes it in-app. A human at the restaurant accepts or refuses it. No capacity math, no opening-hours math, no availability endpoint.

## What changed vs. the previous plan

| Previous plan | New plan |
| --- | --- |
| `Restaurant.max_concurrent_guests` cap + capacity service | **Removed.** No backend capacity logic. |
| `GET /public/restaurants/{id}/availability` | **Removed.** Frontend renders opening hours itself; the backend doesn't gate slot selection. |
| Opening-hours validation on create | **Removed.** Frontend constrains the picker; backend trusts the payload time. |
| Customer create immediately produces `ACTIVE` reservation | Customer create produces `waiting` reservation + email to owner. |
| `ReservationStatus = active/honored/cancelled/no_show` | **Split**: `ReservationStatus = waiting/accepted/refused/canceled` for the request; `TableReservationStatus = active/honored/cancelled/no_show` for the table-binding lifecycle. |
| No staff-side approval route | New routes for the owner to **accept** or **refuse** a waiting request. |

## Decisions

- **Booking model:** still party-size only, no table coupling on create. Staff bind tables on arrival via the existing `PATCH /tables/{id}/status` flow.
- **Approval is manual.** The backend never auto-accepts. The owner accepts or refuses from the dashboard.
- **Phone capture** stays as per the previous plan (required on every customer-created reservation; populates `customer.phone` first time; never overwrites a different existing profile phone).
- **Notification:** email to the restaurant's `email` address using **fastapi-mail**, plus an in-app pending-list endpoint for the owner.
- **No opening-hours / capacity validation server-side.** `reserved_at` must be a valid datetime and (still) strictly in the future. That's it.

## Data model

- **Drop** `restaurant.max_concurrent_guests`. New Alembic migration that down-revises [c4d3e2b1a0f9](alembic/versions/c4d3e2b1a0f9_add_max_concurrent_guests_to_restaurant.py). Remove the field from `RestaurantBase` / `RestaurantUpdate` in [app/schemas/restaurant_schemas.py](app/schemas/restaurant_schemas.py).
- **Split the enum** in [app/schemas/restaurant_table_schemas.py](app/schemas/restaurant_table_schemas.py):

  ```python
  class ReservationStatus(str, Enum):
      WAITING  = "waiting"
      ACCEPTED = "accepted"
      REFUSED  = "refused"
      CANCELED = "canceled"

  class TableReservationStatus(str, Enum):
      ACTIVE    = "active"
      HONORED   = "honored"
      CANCELLED = "cancelled"
      NO_SHOW   = "no_show"
  ```

  - Update `TableReservation.status` and all callers in [app/routers/restaurant_table.py](app/routers/restaurant_table.py) and [app/services/table_status_service.py](app/services/table_status_service.py) to use `TableReservationStatus`.
  - Update `Reservation.status` default to `ReservationStatus.WAITING`.
  - Schema migration (Alembic) updates both enum types. Existing rows: in dev/SQLite the column is just a string, so we'll migrate values (`active → accepted`, `cancelled → canceled`); on Postgres we'll `ALTER TYPE` (drop & recreate is easier for v1).

## Backend changes

### Step 1 — Migration

One Alembic revision:

1. `op.drop_column('restaurant', 'max_concurrent_guests')`.
2. Convert existing `reservation.status` values to the new enum (`active → accepted`, `cancelled → canceled`, others left as-is or mapped — to be decided when writing the migration).

### Step 2 — Strip removed code

- Delete [app/services/reservation_capacity_service.py](app/services/reservation_capacity_service.py).
- Delete `reservation_window` and `iter_slot_times` from [app/services/opening_hours_service.py](app/services/opening_hours_service.py). Keep `compute_open_status` and `is_within_opening_hours` (still used for the public detail endpoint / informational rendering).
- Delete `RESERVATION_SLOT_MINUTES` and `RESERVATION_GRID_MINUTES` from [app/contants.py](app/contants.py).
- Delete `AvailabilitySlot` and `get_restaurant_availability` from [app/routers/public_restaurants.py](app/routers/public_restaurants.py).

### Step 3 — Email service

New module `app/services/email_service.py` using **fastapi-mail**:

```python
from fastapi_mail import FastMail, MessageSchema, MessageType

async def send_reservation_request_email(
    restaurant_email: str,
    *,
    customer_name: str,
    customer_phone: str,
    reserved_at: datetime,
    party_size: int,
    note: str | None,
) -> None: ...
```

- Configure `FastMail` with env-driven `ConnectionConfig` (`MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`, `MAIL_SERVER`, `MAIL_PORT`, `MAIL_STARTTLS`, `MAIL_SSL_TLS`). Add a config block in [app/configs/](app/configs/).
- The send is fired via FastAPI `BackgroundTasks` from the create endpoint so the HTTP response isn't blocked by SMTP.
- Add `fastapi-mail` to [requirements.txt](requirements.txt).

### Step 4 — Customer reservation create

[app/routers/customers_reservations.py](app/routers/customers_reservations.py) `POST /customers/me/reservations`:

1. Resolve restaurant (404 if missing / disabled).
2. Validate `reserved_at` is strictly in the future. 422 otherwise. **No opening-hours check. No capacity check.**
3. Apply phone reconciliation (unchanged from previous plan):
   - `customer.phone is None` → write `payload.phone` onto `customer.phone`.
   - `customer.phone == payload.phone` → nothing extra.
   - `customer.phone != payload.phone` → store on `Reservation.phone` only.
4. Create `Reservation` with `status=ReservationStatus.WAITING`, `customer_id`, `restaurant_id`, name from profile, phone from payload, `party_size`, `note`.
5. Enqueue `send_reservation_request_email` via `BackgroundTasks`.
6. Return `CustomerReservationPublic`.

`CustomerReservationCreate` schema in [app/schemas/reservation_schemas.py](app/schemas/reservation_schemas.py) stays as-is (phone required, party_size required, etc.).

### Step 5 — Customer list / detail

[GET /customers/me/reservations](app/routers/customers_reservations.py#L107) supports filtering by the new statuses (`?status=waiting|accepted|refused|canceled`). Otherwise unchanged.

[GET /customers/me/reservations/{id}](app/routers/customers_reservations.py#L130) unchanged.

### Step 6 — Customer cancel

[PATCH /customers/me/reservations/{id}/cancel](app/routers/customers_reservations.py#L145):

- Allowed when `status in {WAITING, ACCEPTED}` → set to `CANCELED`.
- If already `CANCELED` → return current state (idempotent).
- If `REFUSED` → 409.
- Cascade to any linked `TableReservation` rows (set them to `TableReservationStatus.CANCELLED`).

### Step 7 — Staff accept / refuse

New router `app/routers/restaurant_reservations.py` (or extend an existing one) gated by the existing staff permission system:

```
GET    /restaurants/me/reservations
         ?status=waiting|accepted|refused|canceled    (defaults to waiting)
         &limit=&offset=
PATCH  /restaurants/me/reservations/{reservation_id}/accept
PATCH  /restaurants/me/reservations/{reservation_id}/refuse
```

- Scoped to `current_user.restaurant_id`.
- `accept`: only from `WAITING`. 409 otherwise.
- `refuse`: only from `WAITING`. 409 otherwise.
- Both bump `updated_at`. No table binding side effects — that's still the `PATCH /tables/{id}/status` job and operates on `TableReservation` independently.
- Required permission: a new `reservations:write` (or reuse `tables:write` — to be decided when wiring permissions).

### Step 8 — Tests

In `tests/`:

- Create succeeds → reservation row has `status=waiting`; email background task is scheduled (assert via dependency override / spy on `FastMail.send_message`).
- Create with empty profile phone populates `customer.phone`.
- Create with a different payload phone does not overwrite `customer.phone`.
- Create fails 422 when `reserved_at` is in the past.
- Create fails 422 when `phone` or `party_size` is missing / malformed.
- Listing filters by each status correctly.
- Customer can cancel a `WAITING` reservation; status flips to `CANCELED`.
- Customer can cancel an `ACCEPTED` reservation; linked `TableReservation` rows become `CANCELLED`.
- Customer cannot cancel a `REFUSED` reservation (409).
- Staff `accept` on a `WAITING` row flips to `ACCEPTED`; on any other status → 409.
- Staff `refuse` on a `WAITING` row flips to `REFUSED`; on any other status → 409.
- Staff cannot accept/refuse a reservation that doesn't belong to their restaurant (403/404).
- (Removed) availability endpoint tests, capacity tests, opening-hours create-time tests.

## Endpoints summary

```
POST   /customers/me/reservations
         body: { restaurant_id, reserved_at, phone, party_size, note? }
GET    /customers/me/reservations[?status=]
GET    /customers/me/reservations/{id}
PATCH  /customers/me/reservations/{id}/cancel

GET    /restaurants/me/reservations[?status=]
PATCH  /restaurants/me/reservations/{id}/accept
PATCH  /restaurants/me/reservations/{id}/refuse
```

Removed: `GET /public/restaurants/{id}/availability`.

## Out of scope

- SMS / phone verification.
- Auto-promotion of `RestaurantTable.status` near `reserved_at`. Staff still bind tables manually.
- Backend enforcement of opening hours / capacity. The frontend renders opening hours and constrains the picker; the backend trusts the payload.
- Email templating / i18n beyond a single plain-text body. Templates can come later.
