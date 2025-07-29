from typing import Union
from datetime import datetime
from sqlmodel import Field

from app.schemas.category_schemas import Category


class CategoryDB(Category, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()