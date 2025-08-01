from enum import Enum
from typing import Union
from pydantic import BaseModel
from sqlmodel import Field, SQLModel

from app.schemas.restaurant_schemas import RestaurantBase, RestaurantPublic


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Union[str, None] = None

class Role(str, Enum):
    SUPER_ADMIN= "super_admin"
    ADMIN= "admin"
    SERVER= "server"
    CASHIER= "cashier"


class UserBase(SQLModel):
    username: str
    email: Union[str, None] = None
    full_name: Union[str, None] = None
    roles: Role
    disabled: bool = True

    restaurant_id: Union[int, None] = Field(default= None,foreign_key= "restaurant.id")

class UserCreate(UserBase):
    password: str

class UserPublic(UserBase):
    id: int

class UserRestaurant(UserBase):
    id: int
    restaurant: RestaurantPublic
    token: Token