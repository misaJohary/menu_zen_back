from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field as PydField, field_validator
from sqlmodel import SQLModel

from app.schemas.restaurant_schemas import RestaurantPublic
from app.schemas.restaurant_table_schemas import ReservationStatus, TableReservationStatus


class CustomerReservationCreate(SQLModel):
    restaurant_id: int
    reserved_at: datetime
    phone: str = PydField(min_length=6, max_length=32)
    party_size: int = PydField(ge=1, le=200)
    note: Optional[str] = PydField(default=None, max_length=500)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("phone must not be empty")
        allowed = set("+0123456789 -()")
        if not all(ch in allowed for ch in cleaned):
            raise ValueError("phone contains invalid characters")
        digits = sum(ch.isdigit() for ch in cleaned)
        if digits < 6:
            raise ValueError("phone must contain at least 6 digits")
        return cleaned


class TableAssignmentPublic(BaseModel):
    id: int
    table_id: int
    status: TableReservationStatus


class CustomerReservationPublic(BaseModel):
    id: int
    reserved_at: datetime
    status: ReservationStatus
    party_size: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime
    restaurant: RestaurantPublic
    assigned_tables: List[TableAssignmentPublic] = []


class StaffReservationPublic(BaseModel):
    id: int
    name: str
    phone: str
    reserved_at: datetime
    status: ReservationStatus
    party_size: Optional[int] = None
    note: Optional[str] = None
    customer_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    assigned_tables: List[TableAssignmentPublic] = []
