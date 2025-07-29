from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.configs.database_configs import SessionDep
from app.models.menu_item_models import MenuDB
from app.schemas.menu_item_schemas import MenuItem, MenuItemCreate, MenuItemUptade
from app.services.auth_service import get_current_active_user


router = APIRouter(tags=["menu_items"], dependencies= [Depends(get_current_active_user)])

@router.post("/menu-items",response_model= MenuItem)
def create_menu(menu: MenuItemCreate, session: SessionDep):
    db_menu= MenuDB.model_validate(menu)
    session.add(db_menu)
    session.commit()
    session.refresh(db_menu)
    return db_menu

@router.patch("/menu-items/{menu_item_id}" ,response_model= MenuItem)
def update_category(menu_id: int, menu: MenuItemUptade, session: SessionDep):
    menu_db = session.get(MenuDB, menu_id)
    if not menu_db:
        raise HTTPException(status_code=404, detail="Menu not found")
    menu_data = menu.model_dump(exclude_unset=True)
    menu_db.sqlmodel_update(menu_data)
    session.add(menu_db)
    session.commit()
    session.refresh(menu_db)
    return menu_db

@router.delete("/menu-items/{menu_item_id}")
def delete_menu(menu_id: int, session: SessionDep):
    menu= session.get(MenuDB, menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    session.delete(menu)
    session.commit()
    return {"ok": True}

@router.get("/menu-items/{menu_id}")
def read_menu(menu_id: int, session: SessionDep) -> MenuItem:
    menu= session.get(MenuDB, menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    return menu

@router.get("/menu-items")
def read_menus(session: SessionDep):
    menu_db = session.exec(select(MenuDB)).scalars().all()
    return menu_db

@router.get("/categories/{category_id}/menu-items/")
def read_menus_by_id_category(category_id: int, session: SessionDep):
    menu_db = session.exec(select(MenuDB).where(MenuDB.category == category_id)).scalars().all()
    return menu_db