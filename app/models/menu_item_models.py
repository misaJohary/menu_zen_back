from typing import Union
from datetime import datetime
from sqlmodel import Field

from app.schemas.menu_item_schemas import MenuItem


class MenuDB(MenuItem, table= True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()