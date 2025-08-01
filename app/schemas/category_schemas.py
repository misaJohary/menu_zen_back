from typing import Optional, Union
from sqlmodel import Field, SQLModel


class CategoryBase(SQLModel):
    name: str = Field(max_length=50, index=True)
    description: Optional[str]= Field(default= None, max_length=500, index=True)
    menu_id: Union[int, None]= Field(default= None, foreign_key="menu.id")
class CategoryCreate(CategoryBase):
    pass

class CategoryPublic(CategoryBase):
    id: int

class CategoryUpdate(CategoryBase):
    name: Optional[str]= Field(default= None, max_length=50)
    description: Optional[str]= Field(default= None, max_length=500)