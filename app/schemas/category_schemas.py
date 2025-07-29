from typing import Optional
from sqlmodel import Field, SQLModel


class Category(SQLModel):
    name: str = Field(max_length=50, index=True)
    description: Optional[str]= Field(default= None, max_length=500, index=True)


class CategoryCreate(Category):
    pass

class CategoryUpdate(Category):
    name: Optional[str]= Field(default= None, max_length=50)
    description: Optional[str]= Field(default= None, max_length=500)