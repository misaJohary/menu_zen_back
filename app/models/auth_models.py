from typing import List, Union
from sqlmodel import Field, SQLModel

from app.schemas.auth_schemas import Role, User, UserCreate

class UserDB(User, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    hashed_psd: str