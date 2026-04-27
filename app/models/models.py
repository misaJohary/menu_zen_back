from enum import Enum
from typing import List, Optional, Union
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint

from app.schemas.auth_schemas import UserBase
from app.schemas.category_schemas import CategoryBase, CategoryTranslationBase
from app.schemas.kitchen_schemas import KitchenBase
from app.schemas.menu_item_schemas import MenuItemBase, MenuItemTranslationBase
from app.schemas.menu_schemas import MenuBase, MenuTranslationBase
from app.schemas.order_menu_item_schemas import OrderMenuItemBase
from app.schemas.order_shemas import OrderBase
from app.schemas.restaurant_schemas import RestaurantBase
from app.schemas.restaurant_table_schemas import (
    ReservationStatus,
    RestaurantTableBase,
    TableStatus,
)


# ── RBAC Enum ─────────────────────────────────────────────────────────────────

class UserPermissionType(str, Enum):
    GRANT = "grant"
    REVOKE = "revoke"



# ── RBAC Models ───────────────────────────────────────────────────────────────

class Role(SQLModel, table=True):
    """Represents a named role with an integer hierarchy level."""
    __tablename__ = "roles"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=50, unique=True)
    level: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)

    # Relationships
    users: List["User"] = Relationship(back_populates="role")
    role_permissions: List["RolePermission"] = Relationship(back_populates="role")


class Permission(SQLModel, table=True):
    """A single action that can be performed on a resource, e.g. orders:read."""
    __tablename__ = "permissions"

    id: Optional[int] = Field(default=None, primary_key=True)
    resource: str = Field(max_length=100)
    action: str = Field(max_length=100)

    # Relationships
    role_permissions: List["RolePermission"] = Relationship(back_populates="permission")
    user_permissions: List["UserPermission"] = Relationship(back_populates="permission")

    class Config:
        table_args = (UniqueConstraint("resource", "action", name="uq_resource_action"),)


class RolePermission(SQLModel, table=True):
    """Many-to-many link between Role and Permission."""
    __tablename__ = "role_permissions"

    role_id: int = Field(foreign_key="roles.id", primary_key=True, ondelete="CASCADE")
    permission_id: int = Field(foreign_key="permissions.id", primary_key=True, ondelete="CASCADE")

    # Relationships
    role: Optional[Role] = Relationship(back_populates="role_permissions")
    permission: Optional[Permission] = Relationship(back_populates="role_permissions")


class UserPermission(SQLModel, table=True):
    """Per-user permission override: explicitly grant or revoke a permission."""
    __tablename__ = "user_permissions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE")
    permission_id: int = Field(foreign_key="permissions.id", ondelete="CASCADE")
    # "grant" or "revoke"
    type: UserPermissionType
    granted_by: Optional[int] = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    granted_at: datetime = Field(default_factory=datetime.now)

    # Relationships
    permission: Optional[Permission] = Relationship(back_populates="user_permissions")

    class Config:
        table_args = (UniqueConstraint("user_id", "permission_id", name="uq_user_permission"),)


# ── Existing Models (unchanged except User) ───────────────────────────────────

class MenuAndMenuItemLink(SQLModel, table=True):
    menu_id: Union[int, None] = Field(default=None, foreign_key="menu.id", primary_key=True)
    menu_item_id: Union[int, None] = Field(default=None, foreign_key="menu_item.id", primary_key=True)


class OrderMenuItem(OrderMenuItemBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    menu_item: Union["MenuItem", None] = Relationship(back_populates="order_menu_items")
    order: Union["Order", None] = Relationship(back_populates="order_menu_items")


class KitchenUserLink(SQLModel, table=True):
    """Many-to-many: Kitchen ↔ User (cooks assigned to kitchens)."""
    __tablename__ = "kitchen_user_link"

    kitchen_id: Optional[int] = Field(
        default=None, foreign_key="kitchen.id", primary_key=True, ondelete="CASCADE"
    )
    user_id: Optional[int] = Field(
        default=None, foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )


class Kitchen(KitchenBase, table=True):
    __tablename__ = "kitchen"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    restaurant: Optional["Restaurant"] = Relationship(back_populates="kitchens")
    menu_items: list["MenuItem"] = Relationship(back_populates="kitchen")
    users: list["User"] = Relationship(
        back_populates="kitchens", link_model=KitchenUserLink
    )


class MenuItemTranslation(MenuItemTranslationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    menu_item_id: Optional[int] = Field(default=None, foreign_key="menu_item.id", ondelete="CASCADE")
    menu_item: Union["MenuItem", None] = Relationship(back_populates="translations")


class MenuItem(MenuItemBase, table=True):
    __tablename__ = "menu_item"

    id: Union[int, None] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    category: Union["Category", None] = Relationship(back_populates="menu_items")
    restaurant: Union["Restaurant", None] = Relationship(back_populates="menu_items")
    kitchen: Optional["Kitchen"] = Relationship(back_populates="menu_items")
    order_menu_items: Union[List[OrderMenuItem], None] = Relationship(back_populates="menu_item")
    translations: List[MenuItemTranslation] = Relationship(back_populates="menu_item")
    menus: Union[List["Menu"], None] = Relationship(
        back_populates="menu_items", link_model=MenuAndMenuItemLink
    )


class Restaurant(RestaurantBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    menus: Union[List["Menu"], None] = Relationship(back_populates="restaurant")
    categories: Union[List["Category"], None] = Relationship(back_populates="restaurant")
    tables: Union[List["RestaurantTable"], None] = Relationship(back_populates="restaurant")
    menu_items: Union[List[MenuItem], None] = Relationship(back_populates="restaurant")
    users: Union[List["User"], None] = Relationship(back_populates="restaurant")
    kitchens: list["Kitchen"] = Relationship(back_populates="restaurant")


class CategoryTranslation(CategoryTranslationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    category_id: Optional[int] = Field(default=None, foreign_key="category.id", ondelete="CASCADE")
    name: str = Field(max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)
    category: Union["Category", None] = Relationship(back_populates="translations")

    class Config:
        table_args = (UniqueConstraint("category_id", "language_code"),)


class Category(CategoryBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    translations: List[CategoryTranslation] = Relationship(back_populates="category")

    menu_items: Union[List["MenuItem"], None] = Relationship(back_populates="category")
    restaurant: Restaurant = Relationship(back_populates="categories")


class MenuTranslation(MenuTranslationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    menu_id: Optional[int] = Field(default=None, foreign_key="menu.id", ondelete="CASCADE")
    name: str = Field(max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)
    menu: Union["Menu", None] = Relationship(back_populates="translations")

    class Config:
        table_args = (UniqueConstraint("category_id", "language_code"),)


class Menu(MenuBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    translations: list[MenuTranslation] = Relationship(back_populates="menu")
    restaurant: Restaurant = Relationship(back_populates="menus")
    menu_items: Union[List["MenuItem"], None] = Relationship(
        back_populates="menus", link_model=MenuAndMenuItemLink
    )


class User(UserBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    hashed_psd: str

    # ── RBAC ───────────────────────────────────────────────────────────────
    # role_id is inherited from UserBase (auth_schemas.py) — no duplicate here
    role: Optional[Role] = Relationship(back_populates="users")
    must_change_password: bool = Field(default=False)
    # ───────────────────────────────────────────────────────────────────────

    restaurant: Restaurant = Relationship(back_populates="users")
    kitchens: list["Kitchen"] = Relationship(
        back_populates="users", link_model=KitchenUserLink
    )

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    orders: Union[List["Order"], None] = Relationship(back_populates="server")
    assigned_tables: List["RestaurantTable"] = Relationship(
        back_populates="server",
        sa_relationship_kwargs={"foreign_keys": "RestaurantTable.server_id"},
    )


class RestaurantTable(RestaurantTableBase, table=True):
    __tablename__ = "restaurant_table"

    id: Union[int, None] = Field(default=None, primary_key=True)
    name: str
    updated_at: datetime = Field(default_factory=datetime.now)
    orders: Union[List["Order"], None] = Relationship(back_populates="r_table")
    restaurant: Restaurant = Relationship(back_populates="tables")
    server: Optional[User] = Relationship(
        back_populates="assigned_tables",
        sa_relationship_kwargs={"foreign_keys": "RestaurantTable.server_id"},
    )
    status_logs: List["TableStatusLog"] = Relationship(back_populates="table")
    table_reservations: List["TableReservation"] = Relationship(back_populates="table")


class Reservation(SQLModel, table=True):
    __tablename__ = "reservation"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    phone: str
    reserved_at: datetime
    status: ReservationStatus = Field(default=ReservationStatus.ACTIVE)
    note: Optional[str] = Field(default=None)
    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    table_reservations: List["TableReservation"] = Relationship(back_populates="reservation")
    created_by: Optional[User] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Reservation.created_by_id"},
    )


class TableReservation(SQLModel, table=True):
    __tablename__ = "table_reservation"

    id: Optional[int] = Field(default=None, primary_key=True)
    reservation_id: int = Field(foreign_key="reservation.id")
    table_id: int = Field(foreign_key="restaurant_table.id")
    status: ReservationStatus = Field(default=ReservationStatus.ACTIVE)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    reservation: Reservation = Relationship(back_populates="table_reservations")
    table: RestaurantTable = Relationship(back_populates="table_reservations")


class TableStatusLog(SQLModel, table=True):
    __tablename__ = "table_status_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="restaurant_table.id")
    changed_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    old_status: TableStatus
    new_status: TableStatus
    changed_at: datetime = Field(default_factory=datetime.now)
    note: Optional[str] = Field(default=None)

    table: RestaurantTable = Relationship(back_populates="status_logs")
    changed_by: Optional[User] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "TableStatusLog.changed_by_id"},
    )


class Order(OrderBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    r_table: RestaurantTable = Relationship(back_populates="orders")
    server: Union[User, None] = Relationship(back_populates="orders")
    order_menu_items: Union[List[OrderMenuItem], None] = Relationship(back_populates="order")