from enum import Enum
from typing import Optional, Union
from sqlmodel import Field, SQLModel

from app.schemas.menu_item_schemas import MenuItemPublic

class OrderMenuItemStatus(str, Enum):
    INIT = "init"
    CANCELED = "canceled"
    READY = "ready"

class OrderMenuItemBase(SQLModel):
    quantity: int = Field(default=1, ge=0)
    notes: Optional[str]= None
    menu_item_id: Union[int, None]= Field(default=None, foreign_key="menu_item.id")
    order_id: Union[int, None]= Field(default=None, foreign_key="order.id", ondelete="CASCADE")
    unit_price: Optional[float]= None
    status: OrderMenuItemStatus = Field(default=OrderMenuItemStatus.INIT)

class OrderMenuItemCreate(OrderMenuItemBase):
    pass

class OrderMenuItemPublic(OrderMenuItemBase):
    id: Optional[int] = None
    menu_item: MenuItemPublic

class OrderMenuItemStatusUpdate(SQLModel):
    status: OrderMenuItemStatus