from typing import List, Optional
from sqlmodel import Field, SQLModel


class KitchenBase(SQLModel):
    restaurant_id: Optional[int] = Field(default=None, foreign_key="restaurant.id")
    name: str
    active: bool = True


class KitchenCreate(KitchenBase):
    pass


class KitchenUpdate(SQLModel):
    name: Optional[str] = None
    active: Optional[bool] = None


class KitchenPublic(KitchenBase):
    id: int


class UserInKitchen(SQLModel):
    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None


class KitchenWithUsers(KitchenPublic):
    users: List[UserInKitchen] = []
