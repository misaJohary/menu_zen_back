from typing import List, Optional, Union
from sqlmodel import Field, SQLModel

from app.translations.translation_model import TranslationModel

class CategoryBase(SQLModel):
    color: Union[str, None]= None
    restaurant_id: Union[int, None]= Field(default=None, foreign_key= "restaurant.id")
    active: bool= True

class CategoryTranslationBase(TranslationModel):
    name: str
    description: Optional[str]

class CategoryTranslationCreate(CategoryTranslationBase):
    name: str = Field(max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)

class CategoryCreate(CategoryBase):
    translations: List[CategoryTranslationCreate]

class CategoryTranslationPublic(CategoryTranslationCreate):
    pass

class CategoryPublic(CategoryBase):
    id: int
    translations: List[CategoryTranslationPublic]

class CategoryTranslationUpdate(CategoryTranslationBase):
    name: Optional[str]= Field(default= None)
    description: Optional[str]= Field(default=None)

class CategoryUpdate(SQLModel):
    color: Optional[str] = None
    restaurant_id: Optional[int] = Field(default=None, foreign_key="restaurant.id")
    translations: Optional[list[CategoryTranslationUpdate]] = None
    active: Optional[bool]= None