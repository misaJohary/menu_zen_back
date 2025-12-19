from enum import Enum
from typing import List, Optional, Union
from pydantic import EmailStr, HttpUrl
from sqlmodel import JSON, Column, Field, SQLModel

from pydantic_extra_types.phone_numbers import PhoneNumber

from app.translations.language_code import LanguageCode


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
    phone: PhoneNumber
    email: EmailStr
    city: str
    lat: float
    long: float

class RestaurantCreate(RestaurantBase):
    pass

class RestaurantUpdate(RestaurantBase):
    name: Optional[str]= Field(default= None)
    description: Optional[str]= Field(default= None)
    logo: Optional[str]= Field(default= None)
    cover: Optional[str]= Field(default= None)
    pictures: Optional[List[str]]= Field(default= None, sa_column=Column(JSON))
    social_media: Optional[List[HttpUrl]]= Field(default= None, sa_column=Column(JSON))
    phone: Optional[PhoneNumber]= Field(default= None)
    email: Optional[EmailStr]= Field(default= None)
    city: Optional[str]= Field(default= None)
    lat: Optional[float]= Field(default= None)
    long: Optional[float]= Field(default= None)

class RestaurantPublic(RestaurantBase):
    id: int