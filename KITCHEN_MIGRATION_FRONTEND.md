# Kitchen Feature — Frontend Migration Guide

This document describes every API change introduced by the Kitchen feature.
Read it top-to-bottom before starting integration work.

---

## 1. What changed at a glance

| Area | Change |
|------|--------|
| New resource | `/kitchens` — full CRUD + cook assignment |
| Existing resource | `menu_item` objects now include a `kitchen_id` field |
| Existing resource | `POST /menu-items` and `PATCH /menu-items/{id}` now accept `kitchen_id` |
| Permissions | Roles `admin`, `server`, and `cook` gained kitchen permissions (auto-seeded on server start) |

---

## 2. New permissions per role

| Role | Permissions gained |
|------|--------------------|
| `admin` | `kitchens:create` `kitchens:read` `kitchens:update` `kitchens:delete` |
| `server` | `kitchens:read` |
| `cook` | `kitchens:read` |

> Permissions are seeded automatically on the next server startup — no manual DB action needed.

---

## 3. New endpoints

All endpoints require a valid Bearer token (`Authorization: Bearer <token>`).
Requests that fail permission checks return **403**.

---

### 3.1 `POST /kitchens` — Create a kitchen

**Required permission:** `kitchens:create` (admin only)

**Request body**

```json
{
  "name": "Main Kitchen",
  "active": true
}
```

> `restaurant_id` is set automatically from the authenticated user — do **not** send it.
> `active` defaults to `true` if omitted.

**Response `200`**

```json
{
  "id": 1,
  "restaurant_id": 3,
  "name": "Main Kitchen",
  "active": true
}
```

---

### 3.2 `GET /kitchens` — List kitchens for the current restaurant

**Required permission:** `kitchens:read` (admin, server, cook)

**Response `200`** — array of kitchen objects.

```json
[
  {
    "id": 1,
    "restaurant_id": 3,
    "name": "Main Kitchen",
    "active": true,
    "users": [
      { "id": 5, "username": "john", "full_name": "John Doe"}
    ]
  },
  {
    "id": 2,
    "restaurant_id": 3,
    "name": "Bar",
    "active": true,
    "users":[]
  }
]
```

---

### 3.3 `GET /kitchens/{kitchen_id}` — Get a single kitchen

**Required permission:** `kitchens:read`

**Path parameter:** `kitchen_id` (integer)

**Response `200`** — single kitchen object.

**Errors**

| Status | Reason |
|--------|--------|
| 404 | Kitchen not found |
| 403 | Kitchen belongs to a different restaurant |

---

### 3.4 `PATCH /kitchens/{kitchen_id}` — Update a kitchen

**Required permission:** `kitchens:update` (admin only)

**Request body** — all fields are optional; send only what you want to change.

```json
{
  "name": "Bar",
  "active": false
}
```

**Response `200`** — updated kitchen object.

---

### 3.5 `DELETE /kitchens/{kitchen_id}` — Delete a kitchen

**Required permission:** `kitchens:delete` (admin only)

**Response `200`**

```json
{ "ok": true }
```

> Menu items that were assigned to this kitchen are **not** deleted — their `kitchen_id` is set to `null` automatically by the database.

---

### 3.6 `POST /kitchens/{kitchen_id}/users/{user_id}` — Assign a cook to a kitchen

**Required permission:** `kitchens:update` (admin only)

**Path parameters:** `kitchen_id`, `user_id` (both integers)

**No request body.**

**Response `200`**

```json
{ "ok": true }
```

**Errors**

| Status | Reason |
|--------|--------|
| 404 | Kitchen or user not found |
| 403 | User belongs to a different restaurant |
| 400 | Target user does not have the `cook` role |

> This operation is **idempotent** — calling it when the assignment already exists is safe and returns `200`.

---

### 3.7 `DELETE /kitchens/{kitchen_id}/users/{user_id}` — Remove a cook from a kitchen

**Required permission:** `kitchens:update` (admin only)

**Response `200`**

```json
{ "ok": true }
```

> If the assignment did not exist, the call still returns `200` (idempotent).

---

## 4. Changed: menu item objects

### 4.1 New field on all menu item responses

Every object returned by `GET /menu-items`, `GET /menu-items/{id}`, `GET /menu-items-order`, etc. now includes:

```json
{
  "id": 12,
  "price": 9.50,
  "active": true,
  "kitchen_id": 1,   // ← NEW — null if no kitchen is assigned
  ...
}
```

**Your UI should handle `kitchen_id: null`** for items not yet assigned to a kitchen.

---

### 4.2 `POST /menu-items` — now accepts `kitchen_id`

Add the optional `kitchen_id` field to the create payload:

```json
{
  "price": 9.50,
  "active": true,
  "category_id": 2,
  "kitchen_id": 1,   // ← NEW (optional, omit or set null for no assignment)
  "translations": [ ... ]
}
```

---

### 4.3 `PATCH /menu-items/{id}` — now accepts `kitchen_id`

```json
{
  "kitchen_id": 1    // ← set to null to un-assign from a kitchen
}
```

---

## 5. TypeScript type reference

```ts
interface Kitchen {
  id: number;
  restaurant_id: number;
  name: string;
  active: boolean;
}

interface KitchenCreate {
  name: string;
  active?: boolean;  // defaults to true
}

interface KitchenUpdate {
  name?: string | null;
  active?: boolean | null;
}

// Existing type updated:
interface MenuItem {
  // ...existing fields...
  kitchen_id: number | null;  // ← NEW
}
```

---

## 6. Integration checklist

- [ ] Menu item list/detail views: display kitchen name when `kitchen_id` is not null (fetch kitchen list once and map by id)
- [ ] Menu item create/edit form: add optional kitchen selector (dropdown from `GET /kitchens`)
- [ ] Admin kitchen management page: CRUD via the 5 kitchen endpoints
- [ ] Admin user management: add "Assign to kitchen" action for users with `role_name === "cook"`
- [ ] Cook-facing view: `GET /kitchens` to show the cook's assigned kitchens (filtered server-side by their restaurant)
- [ ] Handle `kitchen_id: null` gracefully everywhere (show "No kitchen" or leave blank)
- [ ] Verify `403` handling is in place for server/cook users attempting create/update/delete
