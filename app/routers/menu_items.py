from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.configs.database_configs import SessionDep
from app.models.models import MenuItem
from app.schemas.menu_item_schemas import MenuItemBase, MenuItemCreate, MenuItemPublic, MenuItemUptade
from app.services.auth_service import get_current_active_user


router = APIRouter(tags=["menu_items"], dependencies=[Depends(get_current_active_user)])

@router.post("/menu-items",response_model= MenuItemPublic)
def create_menu_item(menu: MenuItemCreate, session: SessionDep):
    db_menu_item= MenuItem.model_validate(menu)
    session.add(db_menu_item)
    session.commit()
    session.refresh(db_menu_item)
    return db_menu_item

@router.patch("/menu-items/{menu_item_id}" ,response_model= MenuItemBase)
def update_menu_item(menu_id: int, menu: MenuItemUptade, session: SessionDep):
    menu_db = session.get(MenuItem, menu_id)
    if not menu_db:
        raise HTTPException(status_code=404, detail="Menu item not found")
    menu_data = menu.model_dump(exclude_unset=True)
    menu_db.sqlmodel_update(menu_data)
    session.add(menu_db)
    session.commit()
    session.refresh(menu_db)
    return menu_db

@router.delete("/menu-items/{menu_item_id}")
def delete_menu_item(menu_id: int, session: SessionDep):
    menu= session.get(MenuItem, menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu item not found")
    session.delete(menu)
    session.commit()
    return {"message": f"successfully deleted {menu.name}"}

@router.get("/menu-items/{menu_item_id}")
def read_menu_item(menu_item_id: int, session: SessionDep) -> MenuItemPublic:
    menu= session.get(MenuItem, menu_item_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return menu

@router.get("/menu-items")
def read_menus_item(session: SessionDep):
    menu_db = session.exec(select(MenuItem)).scalars().all()
    return menu_db

@router.get("/categories/{category_id}/menu-items")
def read_menus_item_by_id_category(category_id: int, session: SessionDep):
    menu_db = session.exec(select(MenuItem).where(MenuItem.category_id == category_id)).scalars().all()
    return menu_db