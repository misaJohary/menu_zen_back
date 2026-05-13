# Customer App API — Implementation Plan

## Goal

The current backend serves restaurant staff (admin/server/cashier/cook). We're
adding a second consumer surface: a **customer-facing app** that lets end users
discover restaurants nearby, browse their menus, reserve a table, place orders,
and leave reviews.

The customer app reuses the same database and the same Restaurant / Menu /
MenuItem / Reservation / Order models, but exposes a **separate set of public
and customer-authenticated endpoints** living under a `/public` and `/customers`
prefix.

---

## Scope (decided)

| Capability | In scope | Notes |
|---|---|---|
| Browse restaurants nearby | ✅ | Lat/long + radius + sort by distance |
| Browse menus / menu items / categories | ✅ | Public, no auth |
| Customer accounts | ✅ (optional) | Anonymous browse; account required for reservations / orders / favorites / reviews |
| Reserve a table | ✅ | Reuses existing `Reservation` + `TableReservation` |
| Place an order | ✅ | Extends existing `Order` model with `customer_id` + `order_type` |
| Reviews & ratings | ✅ | New `RestaurantReview` model |
| Favorites | ✅ | New `Favorite` model |

Out of scope (for now): payments, delivery routing, push notifications, chat
between customer and restaurant. Listed in **Future work** at the bottom.

---

## Architectural decisions

### 1. Two parallel auth scopes

Staff and customers are **different identity domains**. A customer is not a
staff user with a "customer" role — they live in their own table.

- New `Customer` model (separate from `User`).
- New JWT issuer for customers with a distinct claim (`"typ": "customer"`)
  so a customer token cannot impersonate staff and vice versa.
- New dependency `get_current_customer` (mirrors `get_current_active_user`).
- Customer endpoints live under `/customers/...`; staff endpoints unchanged.

### 2. Public vs. customer-authenticated endpoints

- `/public/...` — no auth, no rate-limit-by-user. Browsing only. Cache-friendly.
- `/customers/me/...` — requires customer JWT. All actions tied to an identity.

### 3. Geo search — PostGIS

DB is Postgres, so use **PostGIS** end-to-end. Real geodesic distance, real
spatial index, no in-Python distance math.

- Enable the extension once via migration: `CREATE EXTENSION IF NOT EXISTS postgis;`
- Add a `location geography(POINT, 4326)` column to `restaurant`, populated
  from the existing `lat` / `long`. Keep `lat` / `long` as the source of truth
  (UI editing fields); maintain `location` via a DB trigger or by setting it
  in the `Restaurant` create/update services.
- Create a **GiST index** on `location` for fast radius queries:
  `CREATE INDEX ix_restaurant_location ON restaurant USING GIST (location);`
- Query pattern for `GET /public/restaurants/search`:

  ```sql
  SELECT *,
         ST_Distance(location, ST_MakePoint(:lng, :lat)::geography) / 1000 AS distance_km
  FROM restaurant
  WHERE ST_DWithin(location, ST_MakePoint(:lng, :lat)::geography, :radius_m)
    AND (... other filters: type, city ILIKE q, name ILIKE q ...)
  ORDER BY location <-> ST_MakePoint(:lng, :lat)::geography
  LIMIT :limit OFFSET :offset;
  ```

  `ST_DWithin` on `geography` is index-backed and uses true great-circle
  distance in meters. The `<->` operator gives a fast index-ordered kNN sort.

- SQLModel/SQLAlchemy integration: use the **GeoAlchemy2** package
  (`Geography(geometry_type="POINT", srid=4326)`) for the column type. Add it
  to `requirements.txt`.

### 4. Reuse `Order`, extend it; do not fork

Add nullable customer-related fields to the existing `Order` model rather than
creating a parallel `CustomerOrder`. Staff flow stays untouched (new fields are
optional). See **Model changes** below.

### 5. No backwards-compat shims

All new routes; no changes to existing staff routes. Migration adds new tables
and nullable columns only.

---

## Model changes

### New: `Customer`

```python
class Customer(SQLModel, table=True):
    __tablename__ = "customer"
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    phone: Optional[str] = Field(default=None, index=True)
    full_name: Optional[str] = None
    hashed_psd: str
    disabled: bool = False
    avatar: Optional[str] = None        # uploaded image path
    created_at: datetime
    updated_at: datetime

    favorites: List["Favorite"] = Relationship(back_populates="customer")
    reviews: List["RestaurantReview"] = Relationship(back_populates="customer")
    orders: List["Order"] = Relationship(back_populates="customer")
    reservations: List["Reservation"] = Relationship(back_populates="customer")
```

### New: `Favorite`

```python
class Favorite(SQLModel, table=True):
    __tablename__ = "favorite"
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", ondelete="CASCADE")
    restaurant_id: int = Field(foreign_key="restaurant.id", ondelete="CASCADE")
    created_at: datetime

    class Config:
        table_args = (UniqueConstraint("customer_id", "restaurant_id"),)
```

### New: `RestaurantReview`

```python
class RestaurantReview(SQLModel, table=True):
    __tablename__ = "restaurant_review"
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", ondelete="CASCADE")
    restaurant_id: int = Field(foreign_key="restaurant.id", ondelete="CASCADE")
    rating: int           # 1..5, validated at schema level
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        # one review per customer per restaurant; PATCH to edit
        table_args = (UniqueConstraint("customer_id", "restaurant_id"),)
```

### Extend: `Order`

Add nullable fields — staff orders leave them null:

| New field | Type | Purpose |
|---|---|---|
| `customer_id` | `Optional[int]` FK → `customer.id` | Set when the order originated from the customer app |
| `order_type` | `OrderType` enum: `dine_in` / `pickup` / `delivery` | Default `dine_in` for staff orders |
| `contact_name` | `Optional[str]` | For anonymous pickup orders before login is required |
| `contact_phone` | `Optional[str]` | Same |
| `scheduled_for` | `Optional[datetime]` | Pickup time (if order_type=pickup) |

`restaurant_table_id` (FK to `restaurant_table.id`; the SQLModel relationship
attribute is `r_table`) becomes optional for non-`dine_in` orders.

### Extend: `Reservation`

Add `customer_id: Optional[int]` FK → `customer.id`. Anonymous reservations
(staff-created) keep it null — `name`/`phone` already exist on `Reservation`.

---

## Endpoint catalog

All paths below are **new**; nothing existing is renamed or removed.

### A. Public — restaurant discovery

| Method | Path | Notes |
|---|---|---|
| GET | `/public/restaurants/search` | Query params: `lat`, `long` (both required for nearby), `radius_km` (default 10), `q` (text in name), `type` (`fastfood`/`casual`/`fine_dining`), `city`, `limit` (≤50), `offset`. Returns list sorted by distance ascending. Each item carries `distance_km`. |
| GET | `/public/restaurants/{id}` | Full `RestaurantPublic` payload + aggregated rating (`avg_rating`, `review_count`). |
| GET | `/public/restaurants/{id}/menus` | List of menus for the restaurant. |
| GET | `/public/restaurants/{id}/categories` | Categories. |
| GET | `/public/restaurants/{id}/menu-items` | Query params: `menu_id`, `category_id`, `search`, `limit`, `offset`. |
| GET | `/public/menu-items/{id}` | Single item (validates `restaurant_id` belongs to a non-disabled restaurant). |
| GET | `/public/restaurants/{id}/reviews` | Paginated. `sort` = `recent` / `top` / `low`. |
| GET | `/public/restaurants/{id}/reviews/summary` | `avg`, `count`, `histogram` per star. |

> Some of these duplicate routes that exist today (e.g. `/restaurants/{id}/menus`
> in `menu.py`). The duplicates are intentional: the `/public/...` namespace is
> the *contract* for the customer app and lets us add caching, response shaping
> (omit fields like `email`, `phone` if desired), and rate-limiting independently.

### B. Customer auth

| Method | Path | Notes |
|---|---|---|
| POST | `/customers/register` | Body: `email`, `password`, optional `phone`, `full_name`. Returns `CustomerPublic` + token. |
| POST | `/customers/login` | OAuth2 password form (`username` = email or phone). Returns token. |
| POST | `/customers/refresh` | Optional — refresh-token rotation. Decide later if we use short-lived access tokens. |
| GET | `/customers/me` | Returns current customer. |
| PATCH | `/customers/me` | Update name / phone / avatar. |
| POST | `/customers/me/password` | Change password (requires old password). |
| DELETE | `/customers/me` | Soft-delete (`disabled=True`); hard delete only by admin tooling. |

JWT payload: `{"sub": email, "customer_id": id, "typ": "customer"}`. The
`typ` claim is checked by `get_current_customer` and absent / mismatched
tokens are rejected.

### C. Favorites

| Method | Path | Notes |
|---|---|---|
| GET | `/customers/me/favorites` | List with embedded restaurant summary. |
| POST | `/customers/me/favorites` | Body: `{restaurant_id}`. Idempotent (409 or no-op on duplicate). |
| DELETE | `/customers/me/favorites/{restaurant_id}` | |

### D. Reservations

| Method | Path | Notes |
|---|---|---|
| POST | `/customers/me/reservations` | Body: `restaurant_id`, `reserved_at`, `party_size`, optional `note`. Server picks table(s) or leaves table assignment to staff (status = `active`, no `TableReservation` rows yet). |
| GET | `/customers/me/reservations` | Filter by status; sort by `reserved_at` desc. |
| GET | `/customers/me/reservations/{id}` | Includes `restaurant`, current status, assigned tables (if any). |
| PATCH | `/customers/me/reservations/{id}/cancel` | Customer-driven cancel. Sets `status=cancelled`. Cascades to `TableReservation` (also cancelled). |

> Conflict detection (no double-booking) is out of scope for v1. Staff confirm
> reservations manually as today. Mention this explicitly in the API docs.

### E. Orders (customer-placed)

| Method | Path | Notes |
|---|---|---|
| POST | `/customers/me/orders` | Body: `restaurant_id`, `order_type` (`dine_in`/`pickup`/`delivery`), `restaurant_table_id` (only for dine_in QR flow), `scheduled_for` (for pickup), `items: [{menu_item_id, quantity, note?}]`. Validates all menu items belong to the restaurant. Computes totals server-side from current `menu_item.price`. |
| GET | `/customers/me/orders` | Paginated, filter by status. |
| GET | `/customers/me/orders/{id}` | Full detail with line items + status. |
| PATCH | `/customers/me/orders/{id}/cancel` | Only allowed while status is in an early state (define list: `pending` / `confirmed` only). Once kitchen has accepted, customer must contact restaurant. |

WebSocket broadcast: when a customer order is created, push to staff via the
existing `ws_service` (same channel staff orders use, with `order.source = "customer"`).

### F. Reviews

| Method | Path | Notes |
|---|---|---|
| POST | `/customers/me/reviews` | Body: `restaurant_id`, `rating` (1..5), `comment?`. 409 if a review already exists for this customer/restaurant. |
| GET | `/customers/me/reviews` | Customer's own reviews. |
| PATCH | `/customers/me/reviews/{id}` | Edit own review. |
| DELETE | `/customers/me/reviews/{id}` | |

Optionally gate review creation behind "the customer has at least one delivered
order at this restaurant" — flagged as a v1.1 hardening, not v1.

---

## Files to add / change

### New files

- `app/schemas/customer_schemas.py` — `CustomerBase`, `CustomerCreate`, `CustomerPublic`, `CustomerUpdate`, `CustomerToken`.
- `app/schemas/favorite_schemas.py`
- `app/schemas/review_schemas.py`
- `app/routers/public_restaurants.py` — section A.
- `app/routers/customers_auth.py` — section B.
- `app/routers/customers_favorites.py` — section C.
- `app/routers/customers_reservations.py` — section D.
- `app/routers/customers_orders.py` — section E.
- `app/routers/customers_reviews.py` — section F.
- `app/services/customer_auth_service.py` — mirrors `auth_service.py` but for the customer scope (`create_customer_token`, `get_current_customer`, `authenticate_customer`).
- `app/services/geo_service.py` — query builders / helpers around PostGIS (`ST_DWithin`, `ST_Distance`, point construction from `lat`/`long`).
- Alembic migrations:
  1. `CREATE EXTENSION IF NOT EXISTS postgis;` + add `location geography(POINT,4326)` to `restaurant`, backfill from `lat`/`long`, create GiST index.
  2. New tables: `customer`, `favorite`, `restaurant_review`.
  3. New columns on `order` and `reservation`.

### Modified files

- `app/models/models.py` — add `Customer`, `Favorite`, `RestaurantReview`, relationships on `Restaurant`, new columns on `Order` and `Reservation`. Add `location: Geography(POINT, 4326)` to `Restaurant` (GeoAlchemy2), kept in sync with `lat`/`long` in the create/update services.
- `requirements.txt` — add `GeoAlchemy2` (and `Shapely` if we ever want to inspect geometries in Python).
- `app/schemas/order_shemas.py` — add `OrderType` enum, optional fields.
- `app/main.py` — register the six new routers.

---

## Open questions / deferred decisions

1. **Order payments.** v1 marks orders `pending` and lets staff handle payment in-house. Stripe / mobile money integration is a future task.
2. **Anonymous orders & reservations.** Current decision: account required (customer must register to act). Re-evaluate once we have UX data.
3. **Push notifications** for order status updates — needs APNs/FCM, deferred.
4. **Rate limiting** on `/public/*`. Plan to use `slowapi` or Caddy-level limits; not implemented in this milestone.
5. **Search relevance.** Pure distance sort in v1. Combined "distance + rating + open-now" ranking is a v1.1 task.
6. **Restaurant "open now" status.** Needs business hours model — currently the schema has none. Out of scope; flag for follow-up.
7. **Image hosting** for review photos and customer avatars — reuse the existing `uploads/` path or move to S3? Decision needed before v1 ships.

---

## Suggested implementation order

1. `Customer` model + auth (register/login/me) → smallest end-to-end vertical slice.
2. `/public/restaurants/search` + restaurant detail → unblocks the app's home screen.
3. Public menu/category/item endpoints → unblocks restaurant detail screen.
4. Favorites → simple and tests the auth wiring.
5. Reviews + summary → adds value to discovery.
6. Reservations → reuses existing models, mostly glue.
7. Orders (customer) → biggest piece; do last so the order model changes don't churn earlier work.

Each step ships its own Alembic migration and tests.
