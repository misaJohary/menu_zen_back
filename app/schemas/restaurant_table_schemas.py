from typing import Optional, Union
from sqlmodel import Field, SQLModel


class RestaurantTableBase(SQLModel):
    name: str

    restaurant_id: Union[int, None]= Field(default=None, foreign_key= "restaurant.id")

class RestaurantTablePublic(RestaurantTableBase):
    id: int

class RestaurantTableUpdate(RestaurantTableBase):
    name: Optional[str]= Field(default=None, max_length=10)

class RestaurantTableCreate(RestaurantTableBase):
    pass