import os
from typing import Annotated
from fastapi import Depends
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://menuzen:menuzen@localhost:5432/menuzen",
)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
echo = os.getenv("SQL_ECHO", "false").lower() in ("1", "true", "yes")
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=echo, pool_pre_ping=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
