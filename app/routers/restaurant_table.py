from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.models.models import RestaurantTable, User
from app.schemas.restaurant_table_schemas import RestaurantTableBase, RestaurantTableCreate, RestaurantTableUpdate
from app.services.auth_service import get_current_active_user


router = APIRouter(tags= ["tables"])

@router.post("/tables")
def create_table(table: RestaurantTableCreate, session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    db_table = RestaurantTable.model_validate(table)
    db_table.restaurant_id = current_user.restaurant_id
    session.add(db_table)
    session.commit()
    session.refresh(db_table)
    return db_table

@router.delete("/tables/{table_id}")
def delete_table(table_id: int, session: SessionDep):
    table= session.get(RestaurantTable, table_id)
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    session.delete(table)
    session.commit()
    return table.id

@router.patch("/tables/{table_id}", response_model= RestaurantTableBase)
def update_table(table_id: int, table: RestaurantTableUpdate, session: SessionDep):
    table_db = session.get(RestaurantTable, table_id)
    if not table_db:
        raise HTTPException(status_code=404, detail="Table not found")
    table_data = table.model_dump(exclude_unset= True)

    table_db.sqlmodel_update(table_data)
    session.add(table_db)
    session.commit()
    session.refresh(table_db)
    return table_db

@router.get("/tables")
def read_tables(session: SessionDep, current_user: Annotated[RestaurantTable, Depends(get_current_active_user)]):
    table_db = session.exec(select(RestaurantTable).where(RestaurantTable.restaurant_id == current_user.restaurant_id)).all()
    return table_db