from datetime import time
from enum import Enum
from typing import List, Optional, Union
from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, HttpUrl, field_validator, model_validator
from sqlmodel import JSON, Column, Field, SQLModel

from pydantic_extra_types.phone_numbers import PhoneNumber

from app.translations.language_code import LanguageCode


class OpeningSlot(BaseModel):
    open: str
    close: str

    @field_validator("open", "close")
    @classmethod
    def _validate_hhmm(cls, value: str) -> str:
        try:
            parsed = time.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("must be HH:MM") from exc
        return parsed.strftime("%H:%M")


class OpeningPeriod(BaseModel):
    day: int = Field(ge=0, le=6)
    slots: List[OpeningSlot]

    @model_validator(mode="after")
    def _validate_slots(self) -> "OpeningPeriod":
        if not self.slots:
            raise ValueError("slots must not be empty; omit the day to mark it closed")
        parsed = [(time.fromisoformat(s.open), time.fromisoformat(s.close), s) for s in self.slots]
        for open_t, close_t, _ in parsed:
            if close_t <= open_t:
                raise ValueError("slot close must be strictly after open")
        parsed.sort(key=lambda item: item[0])
        for i in range(len(parsed) - 1):
            if parsed[i][1] > parsed[i + 1][0]:
                raise ValueError("slots must not overlap")
        self.slots = [item[2] for item in parsed]
        return self


class OpeningHours(BaseModel):
    """Weekly opening hours.

    `day` is `0=Monday ... 6=Sunday`. Overnight slots (close <= open) are not
    supported in v1.
    """

    timezone: str
    periods: List[OpeningPeriod] = []

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError("unknown IANA timezone")
        return value

    @model_validator(mode="after")
    def _validate_unique_days(self) -> "OpeningHours":
        days = [p.day for p in self.periods]
        if len(days) != len(set(days)):
            raise ValueError("periods must have unique day values")
        return self


class RestaurantType(str, Enum):
    FASTFOOD = "fastfood"
    CASUAL = "casual"
    FINE_DINING = "fine_dining"

class RestaurantBase(SQLModel):
    name: str
    description: Optional[str]= None
    type: RestaurantType
    languages: Optional[List[LanguageCode]]= Field(default=[LanguageCode.FRENCH], sa_column=Column(JSON))
    type: RestaurantType = Field(default=RestaurantType.CASUAL) 
    logo: Optional[str]= None
    cover: Optional[str]= None
    pictures: Optional[List[str]]= Field(default= [],sa_column=Column(JSON))
    social_media: Optional[List[str]]= Field(default= [],sa_column=Column(JSON))
    opening_hours: Optional[OpeningHours] = Field(default=None, sa_column=Column(JSON))
    phone: PhoneNumber
    email: EmailStr
    city: str
    lat: float
    long: float
    disabled: bool = Field(default=False)

class RestaurantCreate(RestaurantBase):
    pass

class RestaurantUpdate(SQLModel):
    name: Optional[str]= Field(default= None)
    description: Optional[str]= Field(default= None)
    type: Optional[RestaurantType]= Field(default= None)
    languages: Optional[List[LanguageCode]]= Field(default= None, sa_column=Column(JSON))
    logo: Optional[str]= Field(default= None)
    cover: Optional[str]= Field(default= None)
    pictures: Optional[List[str]]= Field(default= None, sa_column=Column(JSON))
    social_media: Optional[List[HttpUrl]]= Field(default= None, sa_column=Column(JSON))
    opening_hours: Optional[OpeningHours] = Field(default=None, sa_column=Column(JSON))
    phone: Optional[PhoneNumber]= Field(default= None)
    email: Optional[EmailStr]= Field(default= None)
    city: Optional[str]= Field(default= None)
    lat: Optional[float]= Field(default= None)
    long: Optional[float]= Field(default= None)
    disabled: Optional[bool]= Field(default= None)

class RestaurantPublic(RestaurantBase):
    id: int