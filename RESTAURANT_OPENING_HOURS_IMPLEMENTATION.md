# Restaurant Opening Hours — Step-by-Step Implementation Guide

Companion to [RESTAURANT_OPENING_HOURS_PLAN.md](RESTAURANT_OPENING_HOURS_PLAN.md).
Follow steps in order; each one is self-contained and produces a checkable
artifact.

---

## Step 0 — Branch & Sanity Check

1. Confirm you are on `feat/opening-time` (you are).
2. Run the test suite once to capture a green baseline:
   ```bash
   pytest -q
   ```
3. Capture the current alembic head (for the migration's `down_revision`):
   ```bash
   alembic heads
   ```
   Expected head right now: `609037c1b399`. Note whatever it actually prints —
   use that value in Step 3.

---

## Step 1 — Add `OpeningHours` Pydantic Models

File: [app/schemas/restaurant_schemas.py](app/schemas/restaurant_schemas.py)

1. Add imports at the top of the file (next to the existing imports):
   ```python
   from datetime import time
   from zoneinfo import available_timezones
   from pydantic import BaseModel, field_validator, model_validator
   ```
2. Above `class RestaurantType(str, Enum):`, add three models:
   - `OpeningSlot` with fields `open: str`, `close: str`.
     - `field_validator("open", "close")`: parse with
       `time.fromisoformat(value)` and re-emit as `"HH:MM"`. Raise `ValueError`
       on failure.
   - `OpeningPeriod` with `day: int = Field(ge=0, le=6)` and
     `slots: list[OpeningSlot]`.
     - `model_validator(mode="after")`:
       - Within each slot, assert `close > open` (parse to `time`).
       - Sort slots by `open` and assert no two slots overlap
         (`slots[i].close <= slots[i+1].open`).
       - Reject empty `slots` (a present day must have at least one slot;
         "closed" is expressed by omitting the day).
   - `OpeningHours` with `timezone: str` and
     `periods: list[OpeningPeriod] = []`.
     - `field_validator("timezone")`: assert value in `available_timezones()`.
     - `model_validator(mode="after")`: assert `day` values are unique across
       `periods`.

3. **Doc string** on `OpeningHours`: state that `day` is `0=Monday … 6=Sunday`,
   and that overnight slots are not supported in v1.

Quick sanity (inline Python — do not commit):
```python
from app.schemas.restaurant_schemas import OpeningHours
OpeningHours(**{"timezone": "Indian/Antananarivo", "periods": [
    {"day": 0, "slots": [{"open": "11:00", "close": "14:30"}]}
]})
```

---

## Step 2 — Wire `opening_hours` Into the Restaurant Schemas

Same file: [app/schemas/restaurant_schemas.py](app/schemas/restaurant_schemas.py)

1. In `RestaurantBase`, add (place it near the other JSON-column fields like
   `pictures` / `social_media`):
   ```python
   opening_hours: Optional[OpeningHours] = Field(
       default=None, sa_column=Column(JSON)
   )
   ```
2. In `RestaurantUpdate`, add the same field with `default=None`:
   ```python
   opening_hours: Optional[OpeningHours] = Field(
       default=None, sa_column=Column(JSON)
   )
   ```
3. `RestaurantPublic` already inherits from `RestaurantBase` → no change.

Verify nothing else broke:
```bash
python -c "from app.schemas.restaurant_schemas import RestaurantCreate, RestaurantPublic, RestaurantUpdate; print('ok')"
```

---

## Step 3 — Alembic Migration

1. Generate an empty migration scaffold:
   ```bash
   alembic revision -m "add opening hours to restaurant"
   ```
2. Open the new file under `alembic/versions/`. Set:
   ```python
   down_revision = "609037c1b399"   # or whatever Step 0 printed
   ```
3. Body:
   ```python
   def upgrade() -> None:
       op.add_column(
           "restaurant",
           sa.Column("opening_hours", sa.JSON(), nullable=True),
       )

   def downgrade() -> None:
       op.drop_column("restaurant", "opening_hours")
   ```
4. Apply:
   ```bash
   alembic upgrade head
   ```
5. Verify in psql / sqlite:
   ```sql
   \d restaurant         -- or `PRAGMA table_info(restaurant);` for sqlite
   ```
   The `opening_hours` column should exist as `JSON` (or `JSON` text in sqlite),
   nullable, default `NULL`.

If the upgrade fails, **do not** edit existing migrations; fix this one and
re-run `alembic downgrade -1 && alembic upgrade head`.

---

## Step 4 — Verify Model Side (No Code Change)

File: [app/models/models.py](app/models/models.py#L169)

`Restaurant` inherits from `RestaurantBase`, so the column should be picked up
automatically. Confirm by:

```bash
python -c "from app.models.models import Restaurant; print('opening_hours' in Restaurant.model_fields)"
```
Expected: `True`.

If it prints `False`, re-check the import order in `models.py` — the schema
file must be importable without errors first.

---

## Step 5 — Smoke-Test the Create Endpoint

No code change here — `POST /restaurants` already calls
`Restaurant.model_validate(restaurant)`, which will copy the new field.

1. Start the dev server:
   ```bash
   uvicorn app.main:app --reload
   ```
2. Hit the endpoint with the canonical payload (use httpie/curl/Insomnia). Body
   should include both `restaurant` and `user` (matches the existing signature
   in [restaurant.py:19](app/routers/restaurant.py#L19)):
   ```json
   {
     "restaurant": {
       "name": "Test",
       "type": "casual",
       "phone": "+261340000000",
       "email": "a@b.c",
       "city": "Tana",
       "lat": -18.9,
       "long": 47.5,
       "opening_hours": {
         "timezone": "Indian/Antananarivo",
         "periods": [
           {"day": 0, "slots": [{"open": "11:00", "close": "14:30"}]}
         ]
       }
     },
     "user": { "...": "..." }
   }
   ```
3. The response should echo `opening_hours` back inside `restaurant`.
4. Hit `GET /public/restaurants/{id}` → confirm `opening_hours` is present and
   identical.

---

## Step 6 — Smoke-Test the Update Endpoint

1. `PATCH /restaurant` with **only** `{ "opening_hours": { ... } }` → replaces
   the saved value.
2. `PATCH /restaurant` with `{ "name": "X" }` (no `opening_hours`) → the
   previously saved `opening_hours` is untouched (this is the `exclude_unset=True`
   semantics already in [restaurant.py:70](app/routers/restaurant.py#L70)).
3. `PATCH /restaurant` with an invalid timezone → 422 from Pydantic.

---

## Step 7 — Tests

Create `tests/test_restaurant_opening_hours.py` (mirror the layout of nearby
test files — check one existing file under `tests/` for the fixture pattern
before writing).

### 7a — Schema-level (no DB)

```python
import pytest
from app.schemas.restaurant_schemas import OpeningHours

VALID = {
    "timezone": "Indian/Antananarivo",
    "periods": [
        {"day": 0, "slots": [
            {"open": "11:00", "close": "14:30"},
            {"open": "18:00", "close": "22:00"},
        ]},
    ],
}

def test_valid_opening_hours_round_trip():
    oh = OpeningHours(**VALID)
    assert oh.periods[0].slots[1].open == "18:00"

@pytest.mark.parametrize("mutate, msg", [
    (lambda d: d.update(timezone="Not/AZone"),              "timezone"),
    (lambda d: d["periods"][0]["slots"].append(
        {"open": "10:00", "close": "12:00"}),               "overlap"),
    (lambda d: d["periods"].append(
        {"day": 0, "slots": [{"open": "08:00", "close": "09:00"}]}),
                                                            "duplicate"),
    (lambda d: d["periods"][0]["slots"][0].update(
        open="14:00", close="11:00"),                       "close"),
    (lambda d: d["periods"][0].update(day=9),               "day"),
])
def test_invalid_opening_hours(mutate, msg):
    import copy
    bad = copy.deepcopy(VALID)
    mutate(bad)
    with pytest.raises(Exception):
        OpeningHours(**bad)
```

### 7b — Endpoint-level (DB)

- `test_create_restaurant_persists_opening_hours`: POST → GET, assert echo.
- `test_get_public_restaurant_includes_opening_hours`: hit
  `/public/restaurants/{id}`, assert payload.
- `test_patch_restaurant_replaces_opening_hours`: PATCH with new value, GET,
  assert replaced.
- `test_patch_other_field_leaves_opening_hours`: save hours, PATCH `name` only,
  GET, assert hours unchanged.
- `test_legacy_restaurant_returns_null_opening_hours`: insert a row directly via
  the session without the field, GET → `opening_hours is None`.

Run:
```bash
pytest tests/test_restaurant_opening_hours.py -q
```

---

## Step 8 — Manual UI Check (if applicable)

If the frontend already consumes `RestaurantPublic`, confirm with the frontend
owner whether they want a v1 renderer for this field. **Not blocking** for
backend merge.

---

## Step 9 — Pre-Merge Checklist

- [ ] `alembic upgrade head` succeeds on a fresh DB.
- [ ] `alembic downgrade -1 && alembic upgrade head` round-trips cleanly.
- [ ] `pytest -q` is fully green.
- [ ] `POST /restaurants` accepts and returns `opening_hours`.
- [ ] `PATCH /restaurant` replaces the value; unrelated patches do not.
- [ ] `GET /public/restaurants/{id}` includes the field.
- [ ] `GET /public/restaurants/search` includes the field on each item.
- [ ] Invalid timezone / overlapping slots / duplicate day all → 422.
- [ ] Legacy rows (NULL column) return `null` cleanly.

---

## Step 10 — PR

Title: `feat(restaurant): add weekly opening hours`

Body: link both
[RESTAURANT_OPENING_HOURS_PLAN.md](RESTAURANT_OPENING_HOURS_PLAN.md) and this
file. Call out:
- `day` semantics (0 = Monday).
- Overnight slots are out of scope for v1.
- `is_open_now` is a possible follow-up.

---

## Rollback Plan

```bash
alembic downgrade -1
```
…and revert the PR. The column is nullable with no default, so no data is lost
on downgrade for restaurants that had no hours set; restaurants that did have
hours set will lose them (acceptable — feature is new).
