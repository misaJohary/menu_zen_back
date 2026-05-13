from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field as PydField

from sqlmodel import SQLModel


class CustomerBase(SQLModel):
    email: EmailStr
    phone: Optional[str] = None
    full_name: Optional[str] = None


class CustomerCreate(CustomerBase):
    password: str = PydField(min_length=8, max_length=128)


class CustomerUpdate(SQLModel):
    phone: Optional[str] = None
    full_name: Optional[str] = None
    avatar: Optional[str] = None


class CustomerPublic(SQLModel):
    id: int
    email: EmailStr
    phone: Optional[str] = None
    full_name: Optional[str] = None
    avatar: Optional[str] = None
    created_at: datetime


class CustomerToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer: CustomerPublic


class CustomerPasswordChange(BaseModel):
    old_password: str
    new_password: str = PydField(min_length=8, max_length=128)
