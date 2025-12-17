from typing import List, Optional, Union
from sqlmodel import Field, SQLModel

from app.translations.translation_model import TranslationModel

class MenuTranslationBase(TranslationModel):
    name: str
    description: str
    
class MenuBase(SQLModel):
    active: bool
    restaurant_id: Union[int, None]= Field(default=None, foreign_key= "restaurant.id")

class MenuCreate(MenuBase):
    translations: List[MenuTranslationBase]

class MenuTranslationPublic(MenuTranslationBase):
    id: int

class MenuPublic(MenuBase):
    id: int
    translations: List[MenuTranslationPublic]

class MenuUpdate(MenuBase):
    translations: Optional[List[MenuTranslationBase]]= Field(default=None)
    active: Optional[bool]= Field(default=None)