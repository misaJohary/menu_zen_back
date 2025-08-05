from typing import Optional
from sqlmodel import Field, SQLModel

from app.schemas.menu_item_schemas import MenuItemPublic

class OrderMenuItemBase(SQLModel):
    quantity: int = Field(default=1, gt=0)
    notes: Optional[str]= None

class OrderMenuItemCreate(OrderMenuItemBase):
    menu_item_id: int

class OrderMenuItemPublic(OrderMenuItemBase):
    menu_item: MenuItemPublic