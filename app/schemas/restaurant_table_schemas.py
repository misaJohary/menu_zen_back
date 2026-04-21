from datetime import datetime
from enum import Enum
from typing import Optional, Union
from sqlmodel import Field, SQLModel


class TableStatus(str, Enum):
    FREE     = "free"
    RESERVED = "reserved"
    WAITING  = "waiting"
    ASSIGNED = "assigned"


class ReservationStatus(str, Enum):
    ACTIVE    = "active"
    HONORED   = "honored"
    CANCELLED = "cancelled"
    NO_SHOW   = "no_show"


class RestaurantTableBase(SQLModel):
    name: str

    restaurant_id: Union[int, None]= Field(default=None, foreign_key= "restaurant.id")
    status: TableStatus = Field(default=TableStatus.FREE)
    server_id: Optional[int] = Field(default=None, foreign_key="user.id")
    waiting_since: Optional[datetime] = Field(default=None)
    seats: Optional[int] = Field(default=None)

class ServerPublic(SQLModel):
    id: int
    username: str


class ReservationPublic(SQLModel):
    id: int
    name: str
    phone: str
    reserved_at: datetime
    status: ReservationStatus
    note: Optional[str] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class TableReservationPublic(SQLModel):
    id: int
    reservation_id: int
    table_id: int
    status: ReservationStatus
    reservation: ReservationPublic
    created_at: datetime
    updated_at: datetime


class TableStatusLogPublic(SQLModel):
    id: int
    table_id: int
    changed_by_id: Optional[int] = None
    old_status: TableStatus
    new_status: TableStatus
    changed_at: datetime
    note: Optional[str] = None


class RestaurantTablePublic(RestaurantTableBase):
    id: int
    server: Optional[ServerPublic] = None
    active_reservation: Optional[TableReservationPublic] = None


class RestaurantTableUpdate(RestaurantTableBase):
    name: Optional[str]= Field(default=None, max_length=10)

class RestaurantTableCreate(RestaurantTableBase):
    pass


class RestaurantTableStatusUpdate(SQLModel):
    status: TableStatus
    reservation_id: Optional[int] = None
    reservation_name: Optional[str] = None
    reservation_phone: Optional[str] = None
    reservation_at: Optional[datetime] = None
    reservation_note: Optional[str] = None