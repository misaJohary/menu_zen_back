from typing import Optional
from sqlmodel import Field, SQLModel


class CategoryBase(SQLModel):
    name: str = Field(max_length=50, index=True)
    description: Optional[str]= Field(default= None, max_length=500, index=True)


class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(CategoryBase):
    name: Optional[str]= Field(default= None, max_length=50)
    description: Optional[str]= Field(default= None, max_length=500)