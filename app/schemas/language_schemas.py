from sqlmodel import SQLModel


class Language(SQLModel):
    name: str
    code: str