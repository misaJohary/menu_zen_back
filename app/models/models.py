from typing import List, Optional, Union
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint

from app.schemas.auth_schemas import UserBase
from app.schemas.category_schemas import CategoryBase, CategoryTranslationBase
from app.schemas.menu_item_schemas import MenuItemBase, MenuItemTranslationBase
from app.schemas.menu_schemas import MenuBase, MenuTranslationBase
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


class MenuItemTranslation(MenuItemTranslationBase, table= True):
    id: Optional[int] = Field(default=None, primary_key=True)
    menu_item_id: Optional[int] = Field(default=None, foreign_key="menu_item.id", ondelete="CASCADE")
    menu_item: Union["MenuItem", None]= Relationship(back_populates= "translations")


class MenuItem(MenuItemBase, table=True):
    __tablename__ = "menu_item"

    id: Union[int, None] = Field(default=None, primary_key=True)

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    category: Union["Category", None] = Relationship(back_populates="menu_items")

    restaurant: Union["Restaurant", None] = Relationship(back_populates="menu_items")
    order_menu_items: Union[List[OrderMenuItem], None]= Relationship(back_populates="menu_item")
    translations: List[MenuItemTranslation] = Relationship(back_populates= "menu_item")
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

class CategoryTranslation(CategoryTranslationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    category_id: Optional[int] = Field(default=None, foreign_key="category.id", ondelete="CASCADE")
    name: str = Field(max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)
    category: Union["Category", None] = Relationship(back_populates="translations")
    
    class Config:
        # Ensure unique combination of category_id and language_code
        table_args = (UniqueConstraint('category_id', 'language_code'),)

class Category(CategoryBase, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    translations: List[CategoryTranslation] = Relationship(back_populates= "category")

    menu_items: Union[List["MenuItem"], None] = Relationship(back_populates= "category")
    #menu: Union["Menu", None] = Relationship(back_populates= "categories")
    restaurant: Restaurant = Relationship(back_populates= "categories")

class MenuTranslation(MenuTranslationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    menu_id: Optional[int] = Field(default=None, foreign_key="menu.id", ondelete="CASCADE")
    name: str = Field(max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)
    menu: Union["Menu", None] = Relationship(back_populates="translations")
    
    class Config:
        # Ensure unique combination of category_id and language_code
        table_args = (UniqueConstraint('category_id', 'language_code'),)


class Menu(MenuBase, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    translations: list[MenuTranslation] = Relationship(back_populates="menu")
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