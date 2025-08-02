from typing import List
from sqlmodel import Field, SQLModel

from app.schemas.menu_item_schemas import MenuItemPublic
from app.schemas.restaurant_table_schemas import RestaurantTablePublic

class OrderBase(SQLModel):
    restaurant_table_id: int= Field(foreign_key= "restaurant_table.id")

class OrderPublic(OrderBase):
    id: int
    menu_items: list[MenuItemPublic]
    r_table: RestaurantTablePublic


class OrderCreate(OrderBase):
    menu_items_id: List[int]