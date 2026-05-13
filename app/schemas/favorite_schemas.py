from datetime import datetime

from sqlmodel import SQLModel

from app.schemas.restaurant_schemas import RestaurantPublic


class FavoriteCreate(SQLModel):
    restaurant_id: int


class FavoritePublic(SQLModel):
    id: int
    created_at: datetime
    restaurant: RestaurantPublic
