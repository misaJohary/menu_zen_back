# Restaurant Opening Hours — Implementation Plan

## Overview

Allow a restaurant to declare its weekly opening hours at creation time, expose
them in every restaurant detail response, and let the admin update them later.
A restaurant can have **multiple slots per day** (e.g. lunch + dinner) and can
omit days when it is closed. The timezone is stored alongside the schedule so
clients can render local times correctly.

---

## Target Payload Shape

`opening_hours` is a single JSON object on the restaurant, sent in `POST /restaurants`,
`PATCH /restaurant` and returned by every restaurant response (admin + public).

```json
"opening_hours": {
  "timezone": "Indian/Antananarivo",
  "periods": [
    {
      "day": 0,
      "slots": [
        { "open": "11:00", "close": "14:30" },
        { "open": "18:00", "close": "22:00" }
      ]
    },
    {
      "day": 5,
      "slots": [
        { "open": "09:00", "close": "15:00" },
        { "open": "17:00", "close": "23:00" }
      ]
    }
  ]
}
```

- `day`: integer `0..6`, where `0 = Monday … 6 = Sunday` (ISO weekday minus 1).
  This must be documented on the schema docstring.
- `slots`: ordered list of open/close pairs for that day. Days not listed in
  `periods` are treated as closed.
- `open` / `close`: `"HH:MM"` 24-hour strings.
- `timezone`: IANA timezone name (validated against `zoneinfo`).

Rationale for one object (instead of a separate table):
- Schedule is small (≤ 7 days × few slots), always read together with the
  restaurant, never queried/filtered server-side.
- A JSON column matches the existing pattern in
  [restaurant_schemas.py](app/schemas/restaurant_schemas.py#L20-L25) (`languages`,
  `pictures`, `social_media` are all stored as JSON).
- Avoids an extra join on every public restaurant fetch.

---

## Schema Changes — [app/schemas/restaurant_schemas.py](app/schemas/restaurant_schemas.py)

Add three Pydantic models above `RestaurantBase`:

```python
class OpeningSlot(BaseModel):
    open: str    # "HH:MM"
    close: str   # "HH:MM"

class OpeningPeriod(BaseModel):
    day: int = Field(ge=0, le=6)
    slots: list[OpeningSlot]

class OpeningHours(BaseModel):
    timezone: str               # validated against zoneinfo.available_timezones()
    periods: list[OpeningPeriod] = []
```

Validation rules (Pydantic `field_validator` on `OpeningHours`):
1. `timezone` must be in `zoneinfo.available_timezones()`.
2. `open` and `close` must match `^\d{2}:\d{2}$` and resolve to a valid
   `datetime.time`.
3. Within a slot: `close > open` (overnight slots like `22:00 → 02:00` are
   **out of scope** for v1 — document this; if needed later, allow `close <= open`
   to mean "next day").
4. Within a day: slots must not overlap; sort by `open` and verify.
5. `periods` must not contain duplicate `day` values.

Then update:

| Class | Change |
|---|---|
| `RestaurantBase` | Add `opening_hours: Optional[OpeningHours] = Field(default=None, sa_column=Column(JSON))` |
| `RestaurantUpdate` | Add `opening_hours: Optional[OpeningHours] = Field(default=None, sa_column=Column(JSON))` |
| `RestaurantPublic` | Inherits from `RestaurantBase`, so it picks up the field automatically |

Because `opening_hours` is stored as JSON, SQLModel will serialize/deserialize
through the `OpeningHours` Pydantic model — same pattern as `languages` and
`pictures`.

---

## Model Changes — [app/models/models.py](app/models/models.py#L169)

No relationship change required. `Restaurant` already inherits `RestaurantBase`,
so adding the column on the base is enough. Verify the field is picked up by
SQLModel as a JSON column at table-create time.

---

## Alembic Migration

New revision: `add_opening_hours_to_restaurant`.

```python
def upgrade():
    op.add_column(
        "restaurant",
        sa.Column("opening_hours", sa.JSON(), nullable=True),
    )

def downgrade():
    op.drop_column("restaurant", "opening_hours")
```

- `nullable=True` (no server default) — existing restaurants stay without
  hours and the API returns `null`.
- Down-revision: chain off the current head (run `alembic heads` before
  writing).

---

## Router Changes

### [app/routers/restaurant.py](app/routers/restaurant.py)

- `POST /restaurants` (`create_restaurant`): no code change needed — the body
  is already validated as `RestaurantCreate`, and `Restaurant.model_validate`
  copies `opening_hours` into the new column.
- `PATCH /restaurant` (`update_restaurant`): no code change needed — the
  `for field, value in update_data.items(): setattr(...)` loop already handles
  the new field. Pydantic re-validates the payload, so partial updates only
  accept a **complete** `OpeningHours` object (replacing the whole value, not
  patching individual days). Document this in the route docstring.

### [app/routers/public_restaurants.py](app/routers/public_restaurants.py#L60)

- `RestaurantDetailPublic` inherits from `RestaurantPublic`, so it picks up
  `opening_hours` for free. Confirm `get_restaurant_public` returns it (it will,
  via `RestaurantPublic.model_validate`).
- `RestaurantSearchItem` also inherits; the search response will include
  `opening_hours` for each item. Acceptable size given the cap of 50.

---

## Optional Helper — `is_open_now` (v1.1, not in this plan)

A future iteration may expose `is_open_now: bool` on `RestaurantDetailPublic`,
computed by `zoneinfo.ZoneInfo(opening_hours.timezone)` + the current UTC time.
Out of scope here — flag it in the PR description as a possible follow-up.

---

## Tests

Add to [tests/](tests/) (mirror the existing restaurant test file naming):

1. **Schema validation** (unit, no DB):
   - Invalid timezone → 422.
   - `close <= open` → 422.
   - Overlapping slots within a day → 422.
   - Duplicate `day` → 422.
   - `day` out of `0..6` → 422.
   - Missing `periods` → defaults to `[]` (closed all week).

2. **Create flow** (integration):
   - `POST /restaurants` with the example payload → 200 and persisted.
   - `GET /public/restaurants/{id}` → returns identical `opening_hours`.

3. **Update flow**:
   - `PATCH /restaurant` with a new `opening_hours` replaces the existing one.
   - `PATCH /restaurant` without the field leaves it untouched (already covered
     by `exclude_unset=True` semantics — assert it).

4. **Legacy data**:
   - A restaurant row without `opening_hours` (NULL) returns `null` on the
     public endpoint.

---

## Out of Scope (v1)

- Overnight slots (close < open).
- Special hours / holiday overrides.
- Computed `is_open_now`.
- Filtering search results by "open now".

---

## Files to Touch (Summary)

| File | Change |
|---|---|
| [app/schemas/restaurant_schemas.py](app/schemas/restaurant_schemas.py) | Add `OpeningSlot` / `OpeningPeriod` / `OpeningHours` models + validators; add `opening_hours` to `RestaurantBase` and `RestaurantUpdate` |
| [app/models/models.py](app/models/models.py#L169) | No change (inherits via `RestaurantBase`) — verify only |
| `alembic/versions/<new>_add_opening_hours_to_restaurant.py` | New migration adding nullable JSON column |
| [app/routers/restaurant.py](app/routers/restaurant.py) | Docstring updates only — body code unchanged |
| [app/routers/public_restaurants.py](app/routers/public_restaurants.py) | None — inherited via `RestaurantPublic` |
| [tests/](tests/) | New test cases (validation + create/update/get) |
