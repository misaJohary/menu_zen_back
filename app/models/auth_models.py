from typing import Union
from sqlmodel import Field

from app.schemas.auth_schemas import UserBase

class User(UserBase, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    hashed_psd: str