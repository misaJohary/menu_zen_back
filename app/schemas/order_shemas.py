from typing import List, Optional
from datetime import datetime
from sqlmodel import Field, SQLModel
from enum import Enum

from app.enums.order_type import OrderType
from app.schemas.menu_item_schemas import MenuItemPublic
from app.schemas.order_menu_item_schemas import OrderMenuItemBase, OrderMenuItemCreate, OrderMenuItemPublic
from app.schemas.restaurant_table_schemas import RestaurantTablePublic
from app.schemas.auth_schemas import UserPublic

class OrderStatus(str, Enum):
    CREATED = "created"
    IN_PREPARATION = "in_preparation"
    READY = "ready"
    SERVED = "served"
    CANCELLED = "cancelled"

class PaymentStatus(str, Enum):
    UNPAID = "unpaid"
    PAID = "paid"
    PREPAID = "prepaid"
    REFUNDED = "refunded"

class OrderBase(SQLModel):
    restaurant_table_id: Optional[int]= Field(default=None, foreign_key= "restaurant_table.id")
    order_status: OrderStatus = OrderStatus.CREATED
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    client_name: Optional[str]= Field(default= None)
    server_id: Optional[int]= Field(default= None,foreign_key="user.id")
    total_amount: Optional[int]= Field(default= None)
    order_type: OrderType = Field(default=OrderType.DINE_IN)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id", ondelete="SET NULL")
    contact_name: Optional[str] = Field(default=None)
    contact_phone: Optional[str] = Field(default=None)
    scheduled_for: Optional[datetime] = Field(default=None)
    restaurant_id: Optional[int] = Field(default=None, foreign_key="restaurant.id", ondelete="CASCADE")
    

class OrderPublic(OrderBase):
    id: int
    r_table: RestaurantTablePublic
    server: Optional[UserPublic] = None
    order_menu_items: Optional[list[OrderMenuItemPublic]]
    created_at: datetime

class OrderCreate(OrderBase):
    order_menu_items: list[OrderMenuItemBase]  

class OrderUpdate(OrderBase):
    restaurant_table_id: Optional[int]= Field(default=None, foreign_key= "restaurant_table.id")
    order_status: Optional[OrderStatus] = Field(default=None)
    payment_status: Optional[PaymentStatus] = Field(default= None)
    client_name: Optional[str]= Field(default= None)
    server_id: Optional[int]= Field(default= None,foreign_key="user.id")
    order_menu_items: Optional[list[OrderMenuItemBase]]= Field(default= None)


# ── Customer app schemas ─────────────────────────────────────────────────────

class CustomerOrderItemCreate(SQLModel):
    menu_item_id: int
    quantity: int = Field(ge=1)
    note: Optional[str] = None


class CustomerOrderCreate(SQLModel):
    restaurant_id: int
    order_type: OrderType = OrderType.DINE_IN
    restaurant_table_id: Optional[int] = None
    scheduled_for: Optional[datetime] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    items: list[CustomerOrderItemCreate]


class CustomerOrderItemPublic(SQLModel):
    id: int
    menu_item_id: int
    quantity: int
    unit_price: Optional[float] = None
    notes: Optional[str] = None


class CustomerOrderPublic(SQLModel):
    id: int
    restaurant_id: Optional[int] = None
    restaurant_table_id: Optional[int] = None
    order_type: OrderType
    order_status: OrderStatus
    payment_status: PaymentStatus
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    total_amount: Optional[float] = None
    items: list[CustomerOrderItemPublic] = []
    created_at: datetime
