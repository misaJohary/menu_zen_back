from typing import List, Optional
from datetime import datetime
from sqlmodel import Field, SQLModel
from enum import Enum

from app.schemas.menu_item_schemas import MenuItemPublic
from app.schemas.order_menu_item_schemas import OrderMenuItemBase, OrderMenuItemCreate, OrderMenuItemPublic
from app.schemas.restaurant_table_schemas import RestaurantTablePublic

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
    restaurant_table_id: int= Field(foreign_key= "restaurant_table.id")
    order_status: OrderStatus = OrderStatus.CREATED
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    client_name: Optional[str]= Field(default= None)
    server_id: Optional[int]= Field(default= None,foreign_key="user.id")           
    

class OrderPublic(OrderBase):
    id: int
    r_table: RestaurantTablePublic
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