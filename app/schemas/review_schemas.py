from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field as PydField
from sqlmodel import SQLModel


class ReviewCreate(SQLModel):
    restaurant_id: int
    rating: int = PydField(ge=1, le=5)
    comment: Optional[str] = PydField(default=None, max_length=2000)


class ReviewUpdate(SQLModel):
    rating: Optional[int] = PydField(default=None, ge=1, le=5)
    comment: Optional[str] = PydField(default=None, max_length=2000)


class ReviewCustomer(BaseModel):
    id: int
    display_name: Optional[str] = None
    avatar: Optional[str] = None


class ReviewPublic(BaseModel):
    id: int
    rating: int
    comment: Optional[str] = None
    created_at: datetime
    customer: ReviewCustomer


class ReviewSummary(BaseModel):
    avg: Optional[float] = None
    count: int
    histogram: dict[int, int]
