from typing import Optional, Union
from sqlmodel import Field, SQLModel


class MenuBase(SQLModel):
    name: str
    description: str
    is_active: bool

    restaurant_id: Union[int, None]= Field(default=None, foreign_key= "restaurant.id")

class MenuCreate(MenuBase):
    pass

class MenuPublic(MenuBase):
    id: int

class MenuUpdate(MenuBase):
    name: Optional[str]= Field(default= None, max_length=50)
    description: Optional[str]= Field(default= None, max_length=500)