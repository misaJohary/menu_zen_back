from enum import Enum
from typing import List, Optional, Union
from pydantic import BaseModel
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


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


class User(SQLModel):
    username: str
    email: Union[str, None] = None
    full_name: Union[str, None] = None
    roles: Role
    disabled: bool = True

class UserCreate(User):
    password: str

class UserPublic(User):
    id: int