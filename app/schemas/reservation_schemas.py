from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field as PydField
from sqlmodel import SQLModel

from app.schemas.restaurant_schemas import RestaurantPublic
from app.schemas.restaurant_table_schemas import ReservationStatus


class CustomerReservationCreate(SQLModel):
    restaurant_id: int
    reserved_at: datetime
    party_size: Optional[int] = PydField(default=None, ge=1, le=200)
    note: Optional[str] = PydField(default=None, max_length=500)


class TableAssignmentPublic(BaseModel):
    id: int
    table_id: int
    status: ReservationStatus


class CustomerReservationPublic(BaseModel):
    id: int
    reserved_at: datetime
    status: ReservationStatus
    party_size: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime
    restaurant: RestaurantPublic
    assigned_tables: List[TableAssignmentPublic] = []
