from typing import List, Optional
from sqlalchemy import JSON
from sqlmodel import Column, Field, SQLModel

class MenuItem(SQLModel):
    name: str = Field(index=True)
    description: Optional[str]= None
    price: float= Field(gt= 0)
    picture: Optional[str]= None
    pictures: Optional[List[str]]= Field(sa_column=Column(JSON))
    category: int

class MenuItemCreate(MenuItem):
    pass


class MenuItemUptade(MenuItem):
    name: Optional[str]= Field(default= None)
    description: Optional[str]= Field(default= None)
    price: Optional[float]= Field(gt= 0, default=None)
    picture: Optional[str]= Field(default=None)
    pictures: Optional[List[str]]= Field(default= None, sa_column=Column(JSON))
    category: Optional[int]= Field(default= None)