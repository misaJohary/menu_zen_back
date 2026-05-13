# Customer App API — Step-by-Step Implementation

This document operationalizes [CUSTOMER_APP_API_PLAN.md](CUSTOMER_APP_API_PLAN.md)
into discrete, shippable steps. Each step is small enough to land as a single
PR, ends with a green test suite, and leaves `main` deployable.

The order follows the **Suggested implementation order** in the plan: each
vertical slice unblocks the next one, and the order-model changes — the most
invasive piece — come last to avoid churning earlier work.

---

## Conventions

- One Alembic migration per step. Always run `alembic upgrade head` locally
  before opening the PR and verify the downgrade path.
- Use the `Customer` JWT scope (`typ: "customer"`) for every `/customers/me/*`
  route. Never accept a staff token there, and vice versa.
- Public endpoints (`/public/*`) must never leak staff-only fields (admin
  emails, internal phone numbers, disabled rows).
- All new endpoints get pytest coverage at the router level before merge.
- Schema files mirror the model name: `customer_schemas.py`, `favorite_schemas.py`,
  `review_schemas.py`. Reuse existing schema modules for `Order` / `Reservation`.

---

## Step 0 — Pre-flight

Goal: confirm the environment is ready before touching code.

1. Verify Postgres is the active DB (PostGIS extension only works on Postgres,
   not the local `database.db` SQLite file). Check [docker-compose.yml](docker-compose.yml)
   and the `DATABASE_URL` in [app/configs/](app/configs/).
2. Confirm `alembic` is wired up and `alembic current` returns a head.
3. Read the existing models in [app/models/models.py](app/models/models.py) to
   confirm field names referenced by the plan (`Restaurant.lat`, `Restaurant.long`,
   `Order.restaurant_table_id`, `Reservation.name`, `Reservation.phone`).
4. Read [app/services/auth_service.py](app/services/auth_service.py) to mirror
   its patterns when building `customer_auth_service.py`.

Deliverable: a tiny PR or commit only if pre-flight surfaced inconsistencies
(e.g. missing fields). Otherwise no code change.

---

## Step 1 — `Customer` model + auth (register / login / me)

Smallest end-to-end vertical slice. Establishes the customer identity domain
that every later step depends on.

### 1a. Model + migration

- Add the `Customer` SQLModel class to [app/models/models.py](app/models/models.py)
  exactly as specified in the plan (id, email unique, phone, full_name,
  hashed_psd, disabled, avatar, created_at, updated_at). Leave the
  relationship attributes (`favorites`, `reviews`, `orders`, `reservations`)
  commented out for now — uncomment them as each later step lands.
- Create Alembic migration `add_customer_table`:
  `alembic revision --autogenerate -m "add customer table"`
- Manually inspect the generated migration before committing.

### 1b. Schemas

Create [app/schemas/customer_schemas.py](app/schemas/customer_schemas.py) with:

- `CustomerBase` — email, optional phone, optional full_name.
- `CustomerCreate` — extends `CustomerBase` + `password` (min length 8).
- `CustomerUpdate` — all fields optional, no email change in v1.
- `CustomerPublic` — id, email, phone, full_name, avatar, created_at.
- `CustomerToken` — `access_token`, `token_type`, `customer: CustomerPublic`.
- `CustomerPasswordChange` — `old_password`, `new_password`.

### 1c. Customer auth service

Create [app/services/customer_auth_service.py](app/services/customer_auth_service.py)
mirroring [app/services/auth_service.py](app/services/auth_service.py):

- `hash_password` / `verify_password` — reuse bcrypt helpers from `auth_service`
  if already exported; otherwise import them.
- `create_customer_token(customer)` — JWT payload
  `{"sub": email, "customer_id": id, "typ": "customer", "exp": ...}`.
- `authenticate_customer(db, identifier, password)` — accepts email **or**
  phone in the `identifier` field.
- `get_current_customer(token, db)` — FastAPI dependency. Decodes the JWT,
  **rejects tokens without `typ == "customer"`**, fetches the row, raises 401
  if disabled.

### 1d. Router

Create [app/routers/customers_auth.py](app/routers/customers_auth.py):

| Method | Path | Handler |
|---|---|---|
| POST | `/customers/register` | Create customer; return `CustomerToken`. 409 if email exists. |
| POST | `/customers/login` | `OAuth2PasswordRequestForm`; `username` may be email or phone. |
| GET | `/customers/me` | Returns `CustomerPublic`. |
| PATCH | `/customers/me` | Updates name / phone / avatar. |
| POST | `/customers/me/password` | Verifies `old_password`, sets new one. |
| DELETE | `/customers/me` | Sets `disabled=True`. |

Register the router in [app/main.py](app/main.py).

### 1e. Tests

- Register → login → `me` happy path.
- Register with duplicate email returns 409.
- Login with bad password returns 401.
- Staff JWT rejected by `/customers/me`.
- Customer JWT rejected by an existing staff endpoint.

**Definition of done:** a customer can register, log in, fetch and edit their
profile, and disable their account. Staff endpoints still work unchanged.

---

## Step 2 — PostGIS + `/public/restaurants/search`

Unblocks the customer app's home screen.

### 2a. Dependency + extension

- Add `GeoAlchemy2` to [requirements.txt](requirements.txt).
- Alembic migration `enable_postgis`:
  ```python
  op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
  ```
  Downgrade is a no-op (do not drop the extension — other things may depend on it).

### 2b. Location column

- Add `location: Optional[str] = Field(sa_column=Column(Geography(geometry_type="POINT", srid=4326)))`
  to `Restaurant` in [app/models/models.py](app/models/models.py).
- Migration `add_restaurant_location`:
  1. `ALTER TABLE restaurant ADD COLUMN location geography(POINT, 4326)`.
  2. Backfill: `UPDATE restaurant SET location = ST_SetSRID(ST_MakePoint(long, lat), 4326)::geography WHERE lat IS NOT NULL AND long IS NOT NULL;`
  3. `CREATE INDEX ix_restaurant_location ON restaurant USING GIST (location);`
- Update the existing restaurant create/update service to set `location` from
  `lat`/`long` on every write. (`lat`/`long` remain the editable source of truth.)

### 2c. Geo helper

Create [app/services/geo_service.py](app/services/geo_service.py) with:

- `make_point(lat, long)` — returns the SQLAlchemy expression for
  `ST_MakePoint(long, lat)::geography`.
- `nearby_restaurants_query(db, lat, long, radius_km, filters, limit, offset)`
  — returns a tuple of `(rows, total_count)`. Uses `ST_DWithin` + `ST_Distance`
  and the `<->` operator for ordering.

### 2d. Public router

Create [app/routers/public_restaurants.py](app/routers/public_restaurants.py)
with:

- `GET /public/restaurants/search` — query params per the plan; returns each
  row with `distance_km` (float, 2 decimals).
- `GET /public/restaurants/{id}` — `RestaurantPublic` + `avg_rating: None`,
  `review_count: 0` for now (real values arrive in Step 5).

Register the router in [app/main.py](app/main.py).

### 2e. Tests

- Seed 3 restaurants at known coordinates; assert search returns them in
  distance order with correct `distance_km`.
- Radius filter excludes far rows.
- Disabled restaurants are excluded from public search.
- Text `q` filter works (ILIKE).

**Definition of done:** the customer app can search nearby restaurants and
fetch a single restaurant's public profile.

---

## Step 3 — Public menus, categories, menu-items

Unblocks the restaurant detail screen.

### 3a. Routes

Extend [app/routers/public_restaurants.py](app/routers/public_restaurants.py)
(keep all `/public/*` routes in one router; split if it grows beyond ~250
lines):

| Method | Path |
|---|---|
| GET | `/public/restaurants/{id}/menus` |
| GET | `/public/restaurants/{id}/categories` |
| GET | `/public/restaurants/{id}/menu-items` |
| GET | `/public/menu-items/{id}` |

Each handler:

1. Looks up the restaurant; 404 if missing **or disabled**.
2. Reuses existing queries from [app/routers/menu.py](app/routers/menu.py),
   [app/routers/categories.py](app/routers/categories.py),
   [app/routers/menu_items.py](app/routers/menu_items.py) — extract shared
   pieces into the services layer if duplication grows.
3. Applies `limit` / `offset` (cap `limit` at 50).

### 3b. Response shaping

Define `RestaurantPublic`, `MenuPublic`, `MenuItemPublic`, `CategoryPublic`
in the existing schema modules. These public variants **must not include**
internal-only fields (e.g. cost prices, supplier info if any).

### 3c. Tests

- Disabled restaurant returns 404 from `/public/restaurants/{id}/menus`.
- `menu_id` and `category_id` filters narrow `/public/.../menu-items`.
- `search` query matches case-insensitively.

**Definition of done:** the customer app can render a restaurant detail screen
end-to-end without any authentication.

---

## Step 4 — Favorites

Simplest customer-authenticated feature. Validates the JWT plumbing from Step 1.

### 4a. Model + migration

- Add `Favorite` SQLModel to [app/models/models.py](app/models/models.py) with
  the `(customer_id, restaurant_id)` unique constraint.
- Uncomment `Customer.favorites` and add `Restaurant.favorites` back_populates.
- Migration `add_favorite_table`.

### 4b. Schemas

[app/schemas/favorite_schemas.py](app/schemas/favorite_schemas.py):

- `FavoriteCreate` — `restaurant_id`.
- `FavoritePublic` — id, created_at, embedded `restaurant: RestaurantPublic`.

### 4c. Router

[app/routers/customers_favorites.py](app/routers/customers_favorites.py):

| Method | Path |
|---|---|
| GET | `/customers/me/favorites` |
| POST | `/customers/me/favorites` |
| DELETE | `/customers/me/favorites/{restaurant_id}` |

POST is idempotent — catch the unique-constraint violation and return the
existing row (200) rather than 409.

Register in [app/main.py](app/main.py).

### 4d. Tests

- Cannot favorite without a customer token.
- Duplicate POST returns the same favorite (no 500).
- DELETE removes only the caller's row, never another customer's.

**Definition of done:** customer can mark/unmark restaurants as favorites and
list them.

---

## Step 5 — Reviews + summary

Adds value to discovery; also adds `avg_rating` / `review_count` to the public
restaurant detail.

### 5a. Model + migration

- Add `RestaurantReview` with the `(customer_id, restaurant_id)` unique
  constraint and a CHECK constraint `rating BETWEEN 1 AND 5`.
- Uncomment `Customer.reviews` and add `Restaurant.reviews` back_populates.
- Migration `add_restaurant_review_table`.

### 5b. Schemas

[app/schemas/review_schemas.py](app/schemas/review_schemas.py):

- `ReviewCreate` — `restaurant_id`, `rating` (Pydantic `conint(ge=1, le=5)`),
  optional `comment`.
- `ReviewUpdate` — optional rating + comment.
- `ReviewPublic` — id, rating, comment, created_at, embedded customer
  display name + avatar (no email).
- `ReviewSummary` — `avg: float`, `count: int`, `histogram: dict[int, int]`.

### 5c. Routers

Customer-side [app/routers/customers_reviews.py](app/routers/customers_reviews.py):

| Method | Path |
|---|---|
| POST | `/customers/me/reviews` |
| GET | `/customers/me/reviews` |
| PATCH | `/customers/me/reviews/{id}` |
| DELETE | `/customers/me/reviews/{id}` |

Public-side additions to [app/routers/public_restaurants.py](app/routers/public_restaurants.py):

| Method | Path |
|---|---|
| GET | `/public/restaurants/{id}/reviews` |
| GET | `/public/restaurants/{id}/reviews/summary` |

`sort` values: `recent` (default, `created_at DESC`), `top` (`rating DESC,
created_at DESC`), `low` (`rating ASC, created_at DESC`).

### 5d. Wire summary into restaurant detail

Update `GET /public/restaurants/{id}` so `avg_rating` and `review_count`
come from a `GROUP BY restaurant_id` aggregate (single query, joined; do
not N+1).

### 5e. Tests

- POST a second review for the same restaurant returns 409.
- PATCH updates rating; summary reflects the change.
- DELETE removes the review; summary count decrements.
- Summary histogram sums to `count`.

**Definition of done:** customers can review restaurants once; the public
detail surfaces the aggregate rating.

---

## Step 6 — Customer reservations

Reuses existing `Reservation` and `TableReservation` models.

### 6a. Model change + migration

- Add `customer_id: Optional[int]` FK → `customer.id` to `Reservation`.
- Uncomment `Customer.reservations`; add `Reservation.customer` relationship.
- Migration `add_customer_id_to_reservation` — nullable column, no backfill.

### 6b. Schemas

Extend the existing `reservation_schemas` (or create one if absent — check
first; the plan does not list it under existing schemas) with:

- `CustomerReservationCreate` — `restaurant_id`, `reserved_at`, `party_size`,
  optional `note`.
- `CustomerReservationPublic` — embeds restaurant summary + assigned tables.

### 6c. Router

[app/routers/customers_reservations.py](app/routers/customers_reservations.py):

| Method | Path |
|---|---|
| POST | `/customers/me/reservations` |
| GET | `/customers/me/reservations` |
| GET | `/customers/me/reservations/{id}` |
| PATCH | `/customers/me/reservations/{id}/cancel` |

- POST: create a `Reservation` row with `customer_id` set and `status=active`.
  Copy `name` and `phone` from the customer profile so staff still see them.
  Do **not** create `TableReservation` rows — staff assign tables manually.
- Cancel: only the owning customer; cascades any existing `TableReservation`
  rows to `cancelled` too.

### 6d. Tests

- Customer A cannot view / cancel customer B's reservation.
- Cancel cascades to `TableReservation`.
- Staff-created reservations (no `customer_id`) still work unchanged.

**Definition of done:** customers can book and cancel reservations; staff
flow is unaffected.

---

## Step 7 — Customer-placed orders

Biggest piece. Touches the `Order` model and the WebSocket broadcast path.

### 7a. Enum + model + migration

- Add `OrderType` enum (`dine_in`, `pickup`, `delivery`) to
  [app/enums/](app/enums/) (match the existing enum style there).
- Extend `Order` in [app/models/models.py](app/models/models.py):
  - `customer_id: Optional[int]` FK → `customer.id`
  - `order_type: OrderType` (default `dine_in`)
  - `contact_name: Optional[str]`
  - `contact_phone: Optional[str]`
  - `scheduled_for: Optional[datetime]`
  - `restaurant_table_id` → make nullable (was previously required for staff
    orders; confirmed by reading the current model — column name is
    `restaurant_table_id`; the SQLModel relationship attribute is `r_table`).
- Uncomment `Customer.orders`; add `Order.customer` relationship.
- Migration `extend_order_for_customer_app`:
  - Add columns (nullable).
  - Backfill `order_type='dine_in'` for existing rows.
  - Then `ALTER COLUMN order_type SET NOT NULL`.
  - Alter `restaurant_table_id` to nullable.

### 7b. Schemas

Edit [app/schemas/order_shemas.py](app/schemas/order_shemas.py):

- Add `OrderType` enum import.
- `CustomerOrderCreate` — `restaurant_id`, `order_type`, optional
  `restaurant_table_id` (required iff `order_type == dine_in`), optional
  `scheduled_for`, optional
  `contact_name` / `contact_phone`, `items: list[CustomerOrderItemCreate]`.
- `CustomerOrderItemCreate` — `menu_item_id`, `quantity` (≥ 1), optional
  `note`.
- `CustomerOrderPublic` — full detail with line items.

### 7c. Router

[app/routers/customers_orders.py](app/routers/customers_orders.py):

| Method | Path |
|---|---|
| POST | `/customers/me/orders` |
| GET | `/customers/me/orders` |
| GET | `/customers/me/orders/{id}` |
| PATCH | `/customers/me/orders/{id}/cancel` |

POST handler responsibilities:

1. Validate every `menu_item_id` belongs to `restaurant_id` and is not
   disabled — single `IN` query, not N+1.
2. Validate `restaurant_table_id` belongs to `restaurant_id` when
   `order_type == dine_in`.
3. Compute totals server-side from the current `menu_item.price`. Never trust
   client-sent prices.
4. Persist `Order` + `OrderMenuItem` rows in one transaction.
5. Broadcast via [app/services/ws_service.py](app/services/ws_service.py) to
   the staff channel, with `source = "customer"` in the payload.

Cancel allowed only while `status in {pending, confirmed}`. Once kitchen
accepts, return 409 with a clear message.

### 7d. Tests

- Mixing menu items from two restaurants in one order returns 422.
- Server-computed total ignores client-sent `price`.
- Cancel allowed for `pending`, blocked for `preparing`.
- WS broadcast fires on create (mock the WS service).
- Customer cannot fetch another customer's order.

**Definition of done:** customers can place, list, view, and (early-)cancel
orders; staff see them live in the kitchen view.

---

## Cross-cutting: registration in `main.py`

After each step, confirm [app/main.py](app/main.py) includes all six new
routers:

```python
app.include_router(public_restaurants.router)
app.include_router(customers_auth.router)
app.include_router(customers_favorites.router)
app.include_router(customers_reviews.router)
app.include_router(customers_reservations.router)
app.include_router(customers_orders.router)
```

Each router declares its own prefix (`/public` or `/customers`) and tags so
the OpenAPI docs group cleanly.

---

## Cross-cutting: Alembic discipline

- One migration per step. Never squash.
- Always run `alembic upgrade head` then `alembic downgrade -1` then
  `alembic upgrade head` again before opening the PR — catches non-reversible
  migrations.
- After Step 2, run `python check_heads.py` (already in repo) to ensure no
  branching heads.

---

## Cross-cutting: deferred decisions (do not solve in v1)

These are explicitly out of scope. If a reviewer asks for them, point at the
plan's *Open questions* section:

- Payments (Stripe / mobile money).
- Reservation conflict detection.
- Push notifications.
- Rate limiting on `/public/*`.
- Combined distance + rating + open-now ranking.
- Restaurant business hours.
- Image hosting strategy for review photos / avatars.

---

## Done criteria for the whole milestone

- All 7 steps merged behind a green CI.
- Migrations apply cleanly on a fresh Postgres + PostGIS database.
- Staff app continues to work — no existing endpoint changed shape.
- Manual smoke test against a running server: register → search nearby →
  view menu → favorite → review → reserve → order, end to end, with one
  customer account.
