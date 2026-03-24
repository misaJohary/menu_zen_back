from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.cores.permissions import require_permission
from app.models.models import Menu, MenuTranslation, User
from app.schemas.menu_schemas import MenuBase, MenuCreate, MenuPublic, MenuUpdate
from app.services.auth_service import get_current_active_user
from app.translations.entity_with_translation_creator import EntityWithTranslationsManager

router = APIRouter(tags=["menus"], dependencies=[Depends(get_current_active_user)])

@router.post("/menus", response_model=MenuPublic, dependencies=[require_permission("menu", "create")])
def create_menu(menu: MenuCreate, session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    manager = EntityWithTranslationsManager(session, current_user.restaurant_id)
    return manager.create(
        create_data=menu,
        main_model=Menu,
        translation_model=MenuTranslation,
        foreign_key_field="menu_id"
    )

@router.get("/menus", response_model=List[MenuPublic], dependencies=[require_permission("menu", "read")])
def read_menus(session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    menu_db = session.exec(select(Menu).where(Menu.restaurant_id == current_user.restaurant_id)).all()
    return menu_db

@router.get("/restaurants/{restaurant_id}/menus")
def get_menus_by_restaurant(restaurant_id: int, session: SessionDep):
    menu_db = session.exec(select(Menu).where(Menu.restaurant_id == restaurant_id)).all()
    return menu_db


@router.patch("/menus/{menu_id}", response_model=MenuPublic, dependencies=[require_permission("menu", "update")])
def update_menu(menu_id: int, menu: MenuUpdate, session: SessionDep):
    manager = EntityWithTranslationsManager(session)
    return manager.update(
        entity_id=menu_id,
        update_data=menu,
        main_model=Menu,
        translation_model=MenuTranslation,
        foreign_key_field="menu_id",
        entity_name="Menu"
    )

@router.get("/menus/{menu_id}")
def read_menu(menu_id: int, session: SessionDep) -> MenuBase:
    menu= session.get(Menu, menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    return menu


@router.delete("/menus/{menu_id}", dependencies=[require_permission("menu", "delete")])
def delete_menu(menu_id: int, session: SessionDep):
    menu= session.get(Menu, menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu item not found")
    session.delete(menu)
    session.commit()
    return menu.id