from typing import List, Union
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel

from app.schemas.auth_schemas import UserBase
from app.schemas.category_schemas import CategoryBase
from app.schemas.menu_item_schemas import MenuItemBase
from app.schemas.menu_schemas import MenuBase
from app.schemas.order_menu_item_schemas import OrderMenuItemBase
from app.schemas.order_shemas import OrderBase
from app.schemas.restaurant_schemas import RestaurantBase
from app.schemas.restaurant_table_schemas import RestaurantTableBase


class MenuAndMenuItemLink(SQLModel,table= True):
    menu_id: Union[int, None]= Field(default= None, foreign_key= "menu.id", primary_key= True)
    menu_item_id: Union[int, None]= Field(default= None, foreign_key= "menu_item.id", primary_key= True)

class OrderMenuItem(OrderMenuItemBase, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    menu_item: Union["MenuItem", None] = Relationship(back_populates="order_menu_items")
    order: Union["Order", None]= Relationship(back_populates="order_menu_items")

class MenuItem(MenuItemBase, table=True):
    __tablename__ = "menu_item"

    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    category: Union["Category", None] = Relationship(back_populates="menu_items")

    restaurant: Union["Restaurant", None] = Relationship(back_populates="menu_items")
    order_menu_items: Union[List[OrderMenuItem], None]= Relationship(back_populates="menu_item")

    #orders: Union[list['Order'], None] = Relationship(back_populates= "menu_items", link_model= OrderMenuItemLink)
    menus: Union[List['Menu'], None] = Relationship(back_populates= "menu_items", link_model= MenuAndMenuItemLink)

class Restaurant(RestaurantBase, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    menus: Union[List["Menu"], None]= Relationship(back_populates= "restaurant")
    categories: Union[List["Category"], None]= Relationship(back_populates= "restaurant")
    tables: Union[List["RestaurantTable"], None]= Relationship(back_populates="restaurant")
    menu_items: Union[List[MenuItem], None]= Relationship(back_populates= "restaurant")
    users: Union[List["User"], None]= Relationship(back_populates= "restaurant")

class Category(CategoryBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    menu_items: Union[List["MenuItem"], None] = Relationship(back_populates= "category")
    #menu: Union["Menu", None] = Relationship(back_populates= "categories")
    restaurant: Restaurant = Relationship(back_populates= "categories")

class Menu(MenuBase, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    #categories: Union[List["Category"], None]= Relationship(back_populates= "menu")
    restaurant: Restaurant = Relationship(back_populates= "menus")
    menu_items: Union[List['MenuItem'], None] = Relationship(back_populates= "menus", link_model= MenuAndMenuItemLink)

class User(UserBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    hashed_psd: str

    restaurant: Restaurant = Relationship(back_populates= "users")

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    orders: Union[List["Order"], None]= Relationship(back_populates= "server")

class RestaurantTable(RestaurantTableBase, table= True):

    __tablename__ = "restaurant_table" 
    id: Union[int, None] = Field(default=None, primary_key=True)
    name: str
    orders: Union[List["Order"], None]= Relationship(back_populates= "r_table")
    restaurant: Restaurant = Relationship(back_populates= "tables")

class Order(OrderBase, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    r_table: RestaurantTable= Relationship(back_populates= "orders")
    server: Union[User, None]= Relationship(back_populates="orders")
    order_menu_items: Union[List[OrderMenuItem], None]= Relationship(back_populates="order")