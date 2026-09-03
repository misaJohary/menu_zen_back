# Backend Plan — On-Place (Dine-In) Order via Table QR Code

> **Audience:** Backend team.
> **Companion:** [`FEATURE_PLAN_ON_PLACE_ORDER.md`](./FEATURE_PLAN_ON_PLACE_ORDER.md) (mobile-side spec).
> **API doc to update afterwards:** `apps/menu_zen/CUSTOMER_API_DOCS.md`.

## 1. What we're shipping

Customers scan a table QR (`https://menu-zen.vercel.app/qr/r/{restaurantId}/t/{tableName}`)
and place a dine-in order **without signing in**. The order arrives in
the restaurant kitchen exactly like today's authenticated dine-in
orders — same `CustomerOrder` table, same WebSocket broadcast, same
status lifecycle. The customer tracks the order via a short-lived
`tracking_token` returned at creation time.

The mobile-side decisions that drive backend work:

| # | Decision |
|---|---|
| 1 | Dine-in **does not require authentication** (guest ordering). |
| 2 | No `contact_phone` is collected. |
| 3 | A single **order-level `kitchen_note`** replaces per-item notes for dine-in. |
| 4 | QR codes carry the human **table name** (e.g. `"T1"`), not the internal id. |

---

## 2. Summary of backend changes

| # | Change | Type | Priority |
|---|---|---|---|
| 1 | `GET /public/restaurants/{restaurant_id}/tables/by-name/{table_name}` | **New endpoint** | P0 |
| 2 | `POST /public/restaurants/{restaurant_id}/orders` | **New endpoint** | P0 |
| 3 | `GET /public/orders/{order_id}?token={tracking_token}` | **New endpoint** | P0 |
| 4 | `PATCH /public/orders/{order_id}/cancel?token={tracking_token}` | **New endpoint** | P1 |
| 5 | Add `kitchen_note: string?` to `CustomerOrder` (column + payloads) | **Schema + payload change** | P0 |
| 6 | Add `restaurant_table_name: string?` to `CustomerOrderPublic` response | **Payload change** | P0 |
| 7 | Issue `tracking_token` on guest order creation; persist on the order | **Schema change** | P0 |
| 8 | Broadcast guest orders on the existing `new_order` WebSocket event | **No code change expected** | P0 |
| 9 | Rate-limit + abuse protection on public endpoints | **Infra/middleware** | P0 |

P0 = required for v1 launch. P1 = required before public release but can land in a fast-follow PR.

---

## 3. Schema changes

### 3.1 `customer_orders` table

Add two columns:

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `kitchen_note` | `varchar(500)` | yes | Free-form note from the customer to the kitchen. **Order-level.** Independent of per-item `notes`. |
| `tracking_token` | `varchar(64)` | yes | Set only for guest orders. Random URL-safe string (e.g. 32-byte token, base64url). **Indexed.** Globally unique. Used to authenticate read/cancel by unauthenticated clients. |

Recommended index:
```sql
CREATE UNIQUE INDEX customer_orders_tracking_token_idx
  ON customer_orders (tracking_token)
  WHERE tracking_token IS NOT NULL;
```

Optional: `tracking_token_expires_at TIMESTAMPTZ NULL` if you want
token expiry. Recommendation: do **not** expire — the order status
is terminal after `served` / `cancelled`, and a short physical
lifetime is naturally enforced. Tokens are only useful for orders
the device knows about anyway.

### 3.2 `customer_orders.user_id` (or equivalent)

Must be nullable for guest orders. Verify the current constraint and
drop `NOT NULL` if needed. All other relations remain intact
(`restaurant_id`, `restaurant_table_id`, etc.).

### 3.3 No new tables

`restaurant_tables` already exists and carries the `name` column used
for QR lookup. No changes required.

---

## 4. Endpoint specifications

All endpoints below are **unauthenticated**, mounted under the
existing `/public/*` namespace, served behind the same gateway as the
other public endpoints. Rate limiting is required (see §6).

---

### 4.1 `GET /public/restaurants/{restaurant_id}/tables/by-name/{table_name}`

Resolve a scanned table-name into the internal `restaurant_table_id`.

**Path params**

| Param | Type | Required | Notes |
|---|---|---|---|
| `restaurant_id` | int | yes | |
| `table_name` | string | yes | URL-encoded. Matched case-insensitively against `restaurant_tables.name`. |

**Response 200**

```json
{
  "id": 3,
  "restaurant_id": 7,
  "name": "T1",
  "seats": 4,
  "is_active": true
}
```

**Errors**

| Status | When |
|---|---|
| `404` | Restaurant not found, or no table with that name belongs to the restaurant. |
| `410 Gone` | Table exists but `is_active = false`. Allows the client to show a "not in service" message distinct from "not found". |

**Headers**

`Cache-Control: public, max-age=60` — tables rarely change.

---

### 4.2 `POST /public/restaurants/{restaurant_id}/orders`

Create a guest dine-in order. This is **the only new "write" public
endpoint** and the heart of the feature.

**Path params**

| Param | Type | Required |
|---|---|---|
| `restaurant_id` | int | yes |

**Request body** (`PublicOrderCreate`)

```json
{
  "restaurant_table_id": 3,
  "order_type": "dine_in",
  "contact_name": "Jane",
  "kitchen_note": "Please no peanuts in the salad.",
  "items": [
    { "menu_item_id": 101, "quantity": 2 },
    { "menu_item_id": 117, "quantity": 1, "note": "well done" }
  ]
}
```

**Validation rules**

- `order_type` MUST be `dine_in`. Reject `pickup` / `delivery` with
  `400` — guest pickup/delivery is **out of scope** for v1.
- `restaurant_table_id` is required, must belong to `restaurant_id`,
  must be `is_active = true`.
- `items` must be non-empty.
- Every `menu_item_id` must exist, be active, belong to
  `restaurant_id`.
- `kitchen_note` ≤ 500 chars.
- `contact_name` is optional, ≤ 100 chars.
- `note` per item is optional, ≤ 200 chars.

**Response 201** (`CustomerOrderPublicWithToken`)

```json
{
  "order": {
    "id": 55,
    "restaurant_id": 7,
    "restaurant_table_id": 3,
    "restaurant_table_name": "T1",
    "order_type": "dine_in",
    "order_status": "created",
    "payment_status": "unpaid",
    "contact_name": "Jane",
    "contact_phone": null,
    "kitchen_note": "Please no peanuts in the salad.",
    "scheduled_for": null,
    "total_amount": 54000,
    "items": [
      {
        "id": 901,
        "menu_item_id": 101,
        "quantity": 2,
        "unit_price": 18000,
        "notes": null
      },
      {
        "id": 902,
        "menu_item_id": 117,
        "quantity": 1,
        "unit_price": 18000,
        "notes": "well done"
      }
    ],
    "created_at": "2026-05-28T17:42:11Z"
  },
  "tracking_token": "h_8b6Q7r…wKxR"
}
```

**Errors**

| Status | When |
|---|---|
| `400` | Validation failure (any rule above). |
| `404` | Restaurant or table not found. |
| `410 Gone` | Table is inactive. |
| `422` | A menu item is inactive / removed. |
| `429` | Rate limit exceeded — see §6. |

**Side effects**

- Inserts a row into `customer_orders` with `user_id = NULL`,
  `order_type = 'dine_in'`, and a freshly-generated
  `tracking_token`.
- Inserts `customer_order_items` rows with `unit_price` snapshotted
  from `menu_items.price` at creation time.
- Broadcasts the same `new_order` event on the WebSocket channel
  `/ws/orders/{restaurant_id}` (§6.5 of `CUSTOMER_API_DOCS.md`) so
  the kitchen UI receives it identically to authenticated orders.
- Sets `payment_status = 'unpaid'`.

---

### 4.3 `GET /public/orders/{order_id}?token={tracking_token}`

Fetch a guest order by id, authenticated by the `tracking_token`.

**Path / query params**

| Param | Type | Required |
|---|---|---|
| `order_id` | int | yes |
| `token` | string | yes (query) |

**Response 200** — same shape as `CustomerOrderPublic` extended with
the two new fields (`kitchen_note`, `restaurant_table_name`). Does
**not** return `tracking_token` again.

**Errors**

| Status | When |
|---|---|
| `404` | Order not found, **or** token does not match the order. Use 404 rather than 401/403 to avoid order-id enumeration. |
| `429` | Rate limit exceeded. |

**Headers**

`Cache-Control: no-store` — status changes during the order
lifecycle.

---

### 4.4 `PATCH /public/orders/{order_id}/cancel?token={tracking_token}`

Cancel a guest order. Mirrors the existing
`PATCH /customers/me/orders/{order_id}/cancel`.

**Path / query params** — same as §4.3.

**Response 200** — updated `CustomerOrderPublic`.

**Errors**

| Status | When |
|---|---|
| `404` | Order not found, or token mismatch. |
| `409 Conflict` | Order status is not `created` (already in preparation, ready, served, or already cancelled). |
| `429` | Rate limit exceeded. |

Same authorization model as §4.3 — the `tracking_token` substitutes
for the bearer token.

---

## 5. Auth & security

### 5.1 Why `tracking_token` is safe enough

Guest orders don't carry identity. The threat model is:

- An attacker enumerates `order_id` and tries to read / cancel
  arbitrary orders.

Mitigation:

- The `tracking_token` is **32 random bytes** (≥ 256 bits of entropy).
  Brute force is infeasible.
- All mismatches return `404`, never `401/403`, so the attacker
  cannot distinguish "order doesn't exist" from "wrong token".
- Rate-limit the public endpoints (§6) so guessing is throttled.
- The token is generated server-side; clients never see how it's
  derived.

This matches industry practice for "magic-link" / "ticket" patterns
(e.g. Stripe Checkout sessions, anonymous DocuSign envelopes).

### 5.2 Token rotation / invalidation

Not required for v1. The token is bound to a single order and
becomes irrelevant once the order terminates. If a token is ever
known to leak, ops can clear the column to break the link:

```sql
UPDATE customer_orders SET tracking_token = NULL WHERE id = ?;
```

### 5.3 PII

Guest orders intentionally collect almost no PII:

- `contact_name` — optional, free-text, no validation.
- `contact_phone` — **not collected** (decision §1.2).

Storing only an opaque token + table id + items is materially less
sensitive than the authenticated flow. No special-class data should
end up in `kitchen_note` — the client UI hint must make this clear.
GDPR-class retention follows the same policy as existing
`customer_orders` rows.

---

## 6. Rate limiting & abuse

All four public endpoints **must** be rate-limited. Unlike
`/customers/me/*`, there is no per-user identity to throttle on, so
rate limits are applied by IP (and ideally also by `restaurant_id`
for the write endpoint).

Recommended limits (start strict, relax if telemetry shows false
positives):

| Endpoint | Per IP | Per `(IP, restaurant_id)` | Notes |
|---|---|---|---|
| `GET …/tables/by-name/…` | 60 req / min | — | Cacheable response. |
| `POST …/orders` | 20 req / min | 5 req / min | An attacker shouldn't be able to flood a single restaurant. |
| `GET /public/orders/{id}` | 120 req / min | — | Clients poll for status updates. |
| `PATCH /public/orders/{id}/cancel` | 10 req / min | — | |

Headers on `429`:

- `Retry-After: 30` (or similar).
- `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`
  (RFC 9215 draft).

Additional safety nets:

- **Cap items per order** (server side): max 50 items, max 99 qty
  per item.
- **Cap total amount** sanity check: warn / reject if total exceeds
  a configured threshold (e.g. 5,000,000 in base units) to catch
  buggy / malicious clients.
- **WAF rules**: block requests with suspicious user agents on the
  write endpoint.
- **Bot challenge (optional, post-v1):** if abuse appears, gate the
  write endpoint behind invisible Turnstile / hCaptcha — easy to
  layer because the endpoint is auth-less.

---

## 7. WebSocket broadcasts

No code change expected.

The existing `/ws/orders/{restaurant_id}` channel broadcasts
`new_order`, `order_updated`, etc. Guest orders go through the same
service-layer hook, so once the row is inserted via §4.2, the kitchen
UI receives the event identically. **Please verify** that:

- The `new_order` payload does not assume `user_id IS NOT NULL`.
- The serializer for the WebSocket event includes
  `restaurant_table_name` and `kitchen_note` (so the kitchen UI can
  display them).

---

## 8. Existing endpoint changes (besides the new ones)

### 8.1 `POST /customers/me/orders` (`CUSTOMER_API_DOCS.md` §6.1)

Authenticated dine-in is unchanged behaviorally. Two payload
additions:

- Request body now accepts an optional `kitchen_note: string?`.
- Response now includes `kitchen_note: string?` and
  `restaurant_table_name: string?`.

These are **additive** — no existing client breaks.

### 8.2 `GET /customers/me/orders` & `GET /customers/me/orders/{id}`

Same additive payload changes (`kitchen_note`,
`restaurant_table_name`).

### 8.3 No new endpoint for listing guest orders

The client tracks guest order ids + tokens locally
(`shared_preferences`). There is no `GET /public/orders` (list) —
intentionally, to avoid an enumeration surface. Clients re-fetch each
known order individually via §4.3.

---

## 9. Migration plan

1. **DB migration** — add `kitchen_note`, `tracking_token`, make
   `user_id` nullable, add unique index on `tracking_token`. Zero
   downtime; backfill not needed (new columns default to NULL).
2. **Service-layer changes** — extend the order serializer with the
   two new fields. Add a "guest order" code path that mirrors the
   authenticated path but stamps `user_id = NULL` and generates
   `tracking_token`.
3. **Public endpoint controllers** — add `/public/restaurants/.../tables/by-name/...`,
   `/public/restaurants/.../orders`, `/public/orders/.../`,
   `/public/orders/.../cancel`.
4. **Rate-limit middleware** — apply per §6.
5. **Roll out behind a feature flag** if your infra supports one
   (`feature.public_dine_in = false` by default). Flip on after
   integration testing with a real mobile build.
6. **Update API docs** — extend `apps/menu_zen/CUSTOMER_API_DOCS.md`:
   - Add new section: **§9 — Public Tables** (4.1).
   - Add new section: **§10 — Public Orders (Guest Dine-In)**
     (4.2 / 4.3 / 4.4).
   - Extend **§6 — Orders** with the two new payload fields.

---

## 10. Acceptance / contract tests

Backend should ship these tests with the feature:

1. **Happy path** — POST a guest order, GET it back by token, status
   transitions appear on subsequent GETs, cancel it within `created`
   state.
2. **Token mismatch** returns 404 on GET and PATCH cancel.
3. **Wrong restaurant** (table belongs to a different restaurant)
   returns 400 on POST.
4. **Inactive table** returns 410 on the tables-by-name GET and 410
   on the POST.
5. **Inactive menu item** returns 422 on POST.
6. **Empty items** returns 400 on POST.
7. **Non-`dine_in` order_type** on the public POST returns 400.
8. **WebSocket** — placing a guest order causes a `new_order` event
   on the restaurant channel with `restaurant_table_name` and
   `kitchen_note` populated.
9. **Rate limit** — exceeding the configured POST limit returns 429
   with `Retry-After`.
10. **Idempotency (optional but recommended)** — if the same `POST`
    is replayed with an `Idempotency-Key` header, the same order is
    returned without re-inserting. Out of scope for v1 if your stack
    doesn't already support it.

---

## 11. Open questions for the backend team

1. **Idempotency keys.** Should `POST /public/restaurants/{id}/orders`
   accept an `Idempotency-Key` header to dedupe duplicate submits
   caused by flaky networks? Strongly recommended if cheap to add.
2. **`tracking_token` length / encoding.** Any in-house standard
   (e.g. base32 for human-typeable, base64url for compactness)? Pick
   one and document it.
3. **Storage of `kitchen_note`.** Is `varchar(500)` the right cap,
   or do you prefer `text`? The mobile UI enforces 500.
4. **WAF / bot mitigation.** Is Turnstile / hCaptcha integration
   available in the gateway, or do we lean entirely on rate limiting
   for v1?
5. **`restaurant_table_name` denormalisation.** Should the server
   snapshot the table name into `customer_orders` at creation time
   (in case the staff renames a table later), or always join on read?
   Recommendation: snapshot — table renames shouldn't retroactively
   change the displayed history.
6. **Linking to a customer at later sign-in.** Out of scope for v1.
   Do you want a placeholder field
   (`claimable_by_email VARCHAR NULL`) on `customer_orders` for a
   future "claim this order at sign-up" flow? If yes, add now to
   avoid a second migration.

---

## 12. Out of scope

- Guest pickup / delivery orders.
- Token expiry / rotation.
- Anonymous payments (`payment_status` stays `unpaid` — payment is
  collected by staff at the restaurant).
- Multi-customer orders at one table.
- "Claim guest order on sign-up" flow.
