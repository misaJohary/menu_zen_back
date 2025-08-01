from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.models.models import Menu, Restaurant, User
from app.schemas.menu_schemas import MenuBase, MenuCreate, MenuUpdate
from app.services.auth_service import get_current_active_user

router = APIRouter(tags=["menus"], dependencies=[Depends(get_current_active_user)])

@router.post("/menus", response_model= MenuBase)
def create_menu(menu: MenuCreate, session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    db_menu = Menu.model_validate(menu)
    db_menu.restaurant_id = current_user.restaurant_id
    session.add(db_menu)
    session.commit()
    session.refresh(db_menu)
    return db_menu


@router.get("/menus")
def read_menus(session: SessionDep):
    menu_db = session.exec(select(Menu)).all()
    return menu_db

@router.get("/restaurants/{restaurant_id}/menus")
def get_menus_by_restaurant(restaurant_id: int, session: SessionDep):
    menu_db = session.exec(select(Menu).where(Menu.restaurant_id == restaurant_id)).all()
    return menu_db


@router.patch("/menus/{menu_id}", response_model= MenuBase)
def update_menu(menu_id: int, menu: MenuUpdate, session: SessionDep):
    menu_db = session.get(Menu, menu_id)
    if not menu_db:
        raise HTTPException(status_code=404, detail="Menu not found")
    menu_data = menu.model_dump(exclude_unset= True)
    if menu_data["restaurant_id"]:
        restaurant = session.get(Restaurant, menu_data["restaurant_id"])
        if not restaurant:
            raise HTTPException(status_code=400, detail="Restaurant not found") 

    menu_db.sqlmodel_update(menu_data)
    session.add(menu_db)
    session.commit()
    session.refresh(menu_db)
    return menu_db

@router.get("/menus/{menu_id}")
def read_menu(menu_id: int, session: SessionDep) -> MenuBase:
    menu= session.get(Menu, menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    return menu


@router.delete("/menus/{menu_item_id}")
def delete_menu(menu_id: int, session: SessionDep):
    menu= session.get(Menu, menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu item not found")
    session.delete(menu)
    session.commit()
    return menu

