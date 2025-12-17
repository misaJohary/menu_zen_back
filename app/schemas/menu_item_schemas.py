from typing import List, Optional, Union
from sqlalchemy import JSON
from sqlmodel import Column, Field, SQLModel

from app.schemas.category_schemas import CategoryPublic
from app.schemas.menu_schemas import MenuPublic
from app.translations.translation_model import TranslationModel

class MenuItemTranslationBase(TranslationModel):
    name: str = Field(index=True)
    description: Optional[str]= None

class MenuItemBase(SQLModel):
    price: float= Field(gt= 0)
    picture: Optional[str]= None
    pictures: Union[List[str], None]= Field(default= None,sa_column=Column(JSON))
    category_id: Union[int, None]=Field(default= None, foreign_key="category.id")
    restaurant_id: Union[int, None]=Field(default= None, foreign_key="restaurant.id")
    active: bool= True

class MenuItemCreate(MenuItemBase):
    translations: List[MenuItemTranslationBase]

class MenuItemTranslationPublic(MenuItemTranslationBase):
    id: int

class MenuItemPublic(MenuItemBase):
    id: int
    category: Union[CategoryPublic, None]= None
    menus: Union[List[MenuPublic], None]= None
    translations: List[MenuItemTranslationPublic]

class MenuItemUptade(MenuItemBase):
    id: Optional[int]= Field(default=None)
    translations: Optional[List[MenuItemTranslationBase]]= Field(default=None)
    price: Optional[float]= Field(gt= 0, default=None)
    picture: Optional[str]= Field(default=None)
    pictures: Optional[List[str]]= Field(default= None, sa_column=Column(JSON))
    category_id: Optional[int]= Field(default= None, foreign_key="category.id")
    restaurant_id: Optional[int]=Field(default= None, foreign_key="restaurant.id")
    menus: Optional[List[MenuPublic]]= Field(default=None)
    active: Optional[bool]= Field(default=None)