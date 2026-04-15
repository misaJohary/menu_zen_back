# Kitchen Feature — Implementation Plan

## Context

A restaurant can have multiple kitchens (e.g., a main kitchen and a bar). The new `Kitchen` model
serves two purposes:

1. **MenuItem → Kitchen**: each menu item can be assigned to **zero or one** kitchen (optional FK).
2. **User → Kitchen**: a cook (`role.name = "cook"`) can be assigned to **zero or many** kitchens
   (many-to-many link table).

Following the existing project conventions:
- SQLModel ORM models in `app/models/models.py`, base schemas imported from `app/schemas/`
- Pydantic schemas in `app/schemas/`
- FastAPI router in `app/routers/`
- Alembic migration for every DB change
- Translation table (same pattern as `CategoryTranslation`, `MenuItemTranslation`)
- Permission via `require_permission()` decorator

---

## Step 1 — Schemas (`app/schemas/kitchen_schemas.py`)

Create a new file `app/schemas/kitchen_schemas.py`.

```python
from typing import Optional
from sqlmodel import SQLModel
from app.schemas.menu_schemas import LanguageCode  # reuse existing enum


class KitchenTranslationBase(SQLModel):
    language_code: LanguageCode
    name: str
    description: Optional[str] = None


class KitchenBase(SQLModel):
    restaurant_id: Optional[int] = None   # set from current_user in router
    active: bool = True


class KitchenCreate(KitchenBase):
    translations: list[KitchenTranslationBase]


class KitchenUpdate(SQLModel):
    active: Optional[bool] = None
    translations: Optional[list[KitchenTranslationBase]] = None


class KitchenTranslationPublic(KitchenTranslationBase):
    id: int
    kitchen_id: int


class KitchenPublic(KitchenBase):
    id: int
    translations: list[KitchenTranslationPublic] = []
```

**No changes to other schema files at this step.**

---

## Step 2 — Models (`app/models/models.py`)

### 2a. Import the new schema

Add to the imports block at the top of `app/models/models.py`:

```python
from app.schemas.kitchen_schemas import KitchenBase, KitchenTranslationBase
```

### 2b. Add the M:M link table — `KitchenUserLink`

Insert **before** the `MenuItem` model (order matters for forward references):

```python
class KitchenUserLink(SQLModel, table=True):
    """Many-to-many: Kitchen ↔ User (cooks assigned to kitchens)."""
    __tablename__ = "kitchen_user_link"

    kitchen_id: Optional[int] = Field(
        default=None, foreign_key="kitchen.id", primary_key=True, ondelete="CASCADE"
    )
    user_id: Optional[int] = Field(
        default=None, foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )
```

### 2c. Add `KitchenTranslation` model

```python
class KitchenTranslation(KitchenTranslationBase, table=True):
    __tablename__ = "kitchen_translation"

    id: Optional[int] = Field(default=None, primary_key=True)
    kitchen_id: Optional[int] = Field(
        default=None, foreign_key="kitchen.id", ondelete="CASCADE"
    )
    name: str = Field(max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)

    kitchen: Optional["Kitchen"] = Relationship(back_populates="translations")

    class Config:
        table_args = (UniqueConstraint("kitchen_id", "language_code"),)
```

### 2d. Add `Kitchen` model

```python
class Kitchen(KitchenBase, table=True):
    __tablename__ = "kitchen"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Relationships
    restaurant: Optional["Restaurant"] = Relationship(back_populates="kitchens")
    translations: list[KitchenTranslation] = Relationship(back_populates="kitchen")
    menu_items: list["MenuItem"] = Relationship(back_populates="kitchen")
    users: list["User"] = Relationship(
        back_populates="kitchens", link_model=KitchenUserLink
    )
```

### 2e. Update `MenuItem` model

Add the optional FK field **in `MenuItemBase`** schema (or directly in `MenuItem` if you prefer
not to change the base schema — see note below):

**Option A (preferred — keep base schema clean):** Add `kitchen_id` directly to the `MenuItem`
table model, not the base:

```python
class MenuItem(MenuItemBase, table=True):
    __tablename__ = "menu_item"

    id: Union[int, None] = Field(default=None, primary_key=True)
    kitchen_id: Optional[int] = Field(         # ← NEW
        default=None, foreign_key="kitchen.id", ondelete="SET NULL"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    category: Union["Category", None] = Relationship(back_populates="menu_items")
    restaurant: Union["Restaurant", None] = Relationship(back_populates="menu_items")
    kitchen: Optional["Kitchen"] = Relationship(back_populates="menu_items")  # ← NEW
    order_menu_items: Union[List[OrderMenuItem], None] = Relationship(back_populates="menu_item")
    translations: List[MenuItemTranslation] = Relationship(back_populates="menu_item")
    menus: Union[List["Menu"], None] = Relationship(
        back_populates="menu_items", link_model=MenuAndMenuItemLink
    )
```

### 2f. Update `Restaurant` model

Add the `kitchens` back-reference:

```python
class Restaurant(RestaurantBase, table=True):
    ...
    kitchens: list["Kitchen"] = Relationship(back_populates="restaurant")  # ← NEW
```

### 2g. Update `User` model

Add the `kitchens` many-to-many back-reference:

```python
class User(UserBase, table=True):
    ...
    kitchens: list["Kitchen"] = Relationship(               # ← NEW
        back_populates="users", link_model=KitchenUserLink
    )
```

---

## Step 3 — Alembic Migration

Generate a new migration file under `alembic/versions/`:

```
alembic revision --autogenerate -m "add_kitchen_model"
```

Verify the generated script contains **all** of the following operations (edit manually if needed):

1. **Create `kitchen` table**:
   - `id` (INTEGER PK)
   - `restaurant_id` (INTEGER, FK → `restaurant.id`, nullable)
   - `active` (BOOLEAN, default True)
   - `created_at` (DATETIME)
   - `updated_at` (DATETIME)

2. **Create `kitchen_translation` table**:
   - `id` (INTEGER PK)
   - `kitchen_id` (INTEGER, FK → `kitchen.id`, ON DELETE CASCADE)
   - `language_code` (VARCHAR)
   - `name` (VARCHAR 100)
   - `description` (VARCHAR 500, nullable)
   - UNIQUE constraint on `(kitchen_id, language_code)`

3. **Create `kitchen_user_link` table**:
   - `kitchen_id` (INTEGER, FK → `kitchen.id`, ON DELETE CASCADE, PK)
   - `user_id` (INTEGER, FK → `user.id`, ON DELETE CASCADE, PK)

4. **Add column to `menu_item` table**:
   - `kitchen_id` (INTEGER, FK → `kitchen.id`, ON DELETE SET NULL, nullable)

Run the migration:

```
alembic upgrade head
```

---

## Step 4 — Permissions (`app/main.py`)

### 4a. Add new permission entries

In `_ALL_PERMISSIONS`, add:

```python
("kitchens", "create"),
("kitchens", "read"),
("kitchens", "update"),
("kitchens", "delete"),
```

### 4b. Assign permissions to roles

In `_ROLE_PERMISSIONS`:

```python
"admin": [
    ...existing...,
    ("kitchens", "create"), ("kitchens", "read"),
    ("kitchens", "update"), ("kitchens", "delete"),
],
"server": [
    ...existing...,
    ("kitchens", "read"),
],
"cook": [
    ("menu",     "read"),
    ("orders",   "read"),
    ("kitchens", "read"),   # ← NEW: cooks can see their kitchens
],
```

> **Note**: The `seed_rbac` function is idempotent. New permissions and links are added
> automatically on next startup without duplicating existing data.

---

## Step 5 — Router (`app/routers/kitchens.py`)

Create `app/routers/kitchens.py` with the following endpoints:

### 5a. `POST /kitchens` — Create a kitchen

- Permission: `kitchens:create`
- Body: `KitchenCreate`
- Sets `restaurant_id` from `current_user.restaurant_id`
- Creates `Kitchen` + `KitchenTranslation` records
- Returns: `KitchenPublic`

### 5b. `GET /kitchens` — List kitchens for the current restaurant

- Permission: `kitchens:read`
- Filters by `current_user.restaurant_id`
- Returns: `list[KitchenPublic]`

### 5c. `GET /kitchens/{kitchen_id}` — Get a single kitchen

- Permission: `kitchens:read`
- Validates kitchen belongs to user's restaurant (403 otherwise)
- Returns: `KitchenPublic`

### 5d. `PATCH /kitchens/{kitchen_id}` — Update a kitchen

- Permission: `kitchens:update`
- Validates kitchen belongs to user's restaurant
- Updates `active` flag if provided
- Replaces translations if provided (delete old ones, insert new ones — same pattern as
  `PATCH /categories/{id}`)
- Sets `updated_at = datetime.now()`
- Returns: `KitchenPublic`

### 5e. `DELETE /kitchens/{kitchen_id}` — Delete a kitchen

- Permission: `kitchens:delete`
- Validates kitchen belongs to user's restaurant
- Deletes the kitchen (cascade removes translations and link rows)
- Sets `kitchen_id = NULL` on linked `menu_item` rows via DB `ON DELETE SET NULL`
- Returns: `{"ok": True}`

### 5f. `POST /kitchens/{kitchen_id}/users/{user_id}` — Assign a cook to a kitchen

- Permission: `kitchens:update`
- Validates kitchen belongs to user's restaurant
- Validates the target user belongs to the same restaurant and has `role.name == "cook"`
- Creates `KitchenUserLink` if not already present (idempotent)
- Returns: `KitchenPublic` (with updated user list, or just `{"ok": True}`)

### 5g. `DELETE /kitchens/{kitchen_id}/users/{user_id}` — Remove a cook from a kitchen

- Permission: `kitchens:update`
- Validates kitchen belongs to user's restaurant
- Deletes `KitchenUserLink` row if it exists
- Returns: `{"ok": True}`

---

## Step 6 — Update Existing Schemas & Routers

### 6a. `MenuItemBase` / `MenuItemUptade` schema

In `app/schemas/menu_item_schemas.py`, add to `MenuItemBase`:

```python
kitchen_id: Optional[int] = None
```

And to `MenuItemUptade`:

```python
kitchen_id: Optional[int] = None
```

This lets `POST /menu-items` and `PATCH /menu-items/{id}` accept an optional `kitchen_id`.

### 6b. `MenuItemPublic` schema

Add `kitchen_id` to the public response so clients can read which kitchen an item belongs to.
Optionally add a nested `KitchenPublic` object.

### 6c. `GET /menu-items-order` router

The order-creation menu item listing endpoint (`GET /menu-items-order`) could accept an optional
`kitchen_id` query parameter to filter items by kitchen. This is optional but useful for a
cook-facing view.

---

## Step 7 — Register Router in `app/main.py`

```python
from app.routers import kitchens   # ← NEW import

app.include_router(kitchens.router)
```

---

## Step 8 — Optional: Public kitchen endpoint

For customer-facing or QR-code flows, a public endpoint (no auth required) might be needed:

```
GET /restaurants/{restaurant_id}/kitchens
```

Follow the same pattern as `GET /restaurants/{id}/categories` in `categories.py`.

---

## Implementation Order (Summary)

| # | File | Action |
|---|------|--------|
| 1 | `app/schemas/kitchen_schemas.py` | Create (new file) |
| 2 | `app/models/models.py` | Add `KitchenUserLink`, `KitchenTranslation`, `Kitchen`; update `MenuItem`, `Restaurant`, `User` |
| 3 | `alembic/versions/<hash>_add_kitchen_model.py` | Generate + verify migration |
| 4 | `app/main.py` | Add kitchen permissions to `_ALL_PERMISSIONS` & `_ROLE_PERMISSIONS`; import & register router |
| 5 | `app/routers/kitchens.py` | Create (new file) with all 7 endpoints |
| 6 | `app/schemas/menu_item_schemas.py` | Add `kitchen_id` to `MenuItemBase` & `MenuItemUptade` |
| 7 | `app/routers/menu_items.py` | No changes needed — `kitchen_id` flows through existing create/update logic once schema is updated |

---

## Key Design Decisions

- **`ON DELETE SET NULL`** on `menu_item.kitchen_id`: deleting a kitchen does not delete menu
  items — it just un-assigns them. This is the safest default.
- **`ON DELETE CASCADE`** on `kitchen_translation.kitchen_id` and `kitchen_user_link.kitchen_id`:
  removing a kitchen automatically removes its translations and cook assignments.
- **Translations follow the same pattern** as `Category` / `MenuItem` — a separate table with
  `UNIQUE(kitchen_id, language_code)`.
- **Cook assignment is idempotent**: the `POST /kitchens/{id}/users/{user_id}` endpoint checks for
  an existing link before inserting, matching the style of the codebase.
- **`kitchen_id` is NOT added to `MenuItemBase`** in the schema if it would break existing
  clients; it can be added directly to the `MenuItem` ORM model and exposed only in `MenuItemPublic`
  / `MenuItemUptade`. Choose Option A from Step 2e.
