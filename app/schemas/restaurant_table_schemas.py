from sqlmodel import SQLModel


class RestaurantTableBase(SQLModel):
    name: str

class RestaurantTablePublic(RestaurantTableBase):
    id: int

class RestaurantTableCreate(RestaurantTableBase):
    pass