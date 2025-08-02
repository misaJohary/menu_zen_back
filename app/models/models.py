from typing import List, Union
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel

from app.schemas.auth_schemas import UserBase
from app.schemas.category_schemas import CategoryBase
from app.schemas.menu_item_schemas import MenuItemBase
from app.schemas.menu_schemas import MenuBase
from app.schemas.order_shemas import OrderBase
from app.schemas.restaurant_schemas import RestaurantBase
from app.schemas.restaurant_table_schemas import RestaurantTableBase

class Category(CategoryBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    menu_items: Union[List["MenuItem"], None] = Relationship(back_populates= "category")
    menu: Union["Menu", None] = Relationship(back_populates= "categories")

class OrderMenuItemLink(SQLModel, table= True):
    order_id: Union[int, None]= Field(default= None, foreign_key= "order.id", primary_key= True)
    menu_item_id: Union[int, None]= Field(default= None, foreign_key= "menu_item.id", primary_key= True)

class MenuItem(MenuItemBase, table=True):
    __tablename__ = "menu_item"

    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    category: Union[Category, None] = Relationship(back_populates="menu_items")
    orders: Union[list['Order'], None] = Relationship(back_populates= "menu_items", link_model= OrderMenuItemLink)

class Restaurant(RestaurantBase, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    menus: Union[List["Menu"], None]= Relationship(back_populates= "restaurant")
    users: Union[List["User"], None]= Relationship(back_populates= "restaurant")

class Menu(MenuBase, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    categories: Union[List["Category"], None]= Relationship(back_populates= "menu")

    restaurant: Restaurant = Relationship(back_populates= "menus")

class User(UserBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    hashed_psd: str

    restaurant: Restaurant = Relationship(back_populates= "users")

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

class RestaurantTable(RestaurantTableBase, table= True):

    __tablename__ = "restaurant_table" 
    id: Union[int, None] = Field(default=None, primary_key=True)
    name: str
    orders: Union[List["Order"], None]= Relationship(back_populates= "r_table")

class Order(OrderBase, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    r_table: RestaurantTable= Relationship(back_populates= "orders")
    menu_items: list[MenuItem]= Relationship(back_populates= "orders", link_model= OrderMenuItemLink)