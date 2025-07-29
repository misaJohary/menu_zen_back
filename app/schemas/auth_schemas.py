from enum import Enum
from typing import Union
from pydantic import BaseModel
from sqlmodel import SQLModel


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

class UserCreate(UserBase):
    password: str

class UserPublic(UserBase):
    id: int