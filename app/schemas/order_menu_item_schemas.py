from typing import Optional, Union
from sqlmodel import Field, SQLModel

from app.schemas.menu_item_schemas import MenuItemPublic

class OrderMenuItemBase(SQLModel):
    quantity: int = Field(default=1, ge=0)
    notes: Optional[str]= None
    menu_item_id: Union[int, None]= Field(default=None, foreign_key="menu_item.id")
    order_id: Union[int, None]= Field(default=None, foreign_key="order.id", ondelete="CASCADE")
    unit_price: Optional[float]= None

class OrderMenuItemCreate(OrderMenuItemBase):
    pass

class OrderMenuItemPublic(OrderMenuItemBase):
    menu_item: MenuItemPublic