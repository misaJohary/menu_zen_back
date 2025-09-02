import shutil
from typing import Annotated, List, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Field, select
from pathlib import Path as PathLib
from sqlalchemy.orm import selectinload

from app.configs.database_configs import SessionDep
from app.models.models import Menu, MenuItem, User
from app.schemas.menu_item_schemas import MenuItemBase, MenuItemCreate, MenuItemPublic, MenuItemUptade
from app.schemas.order_menu_item_schemas import OrderMenuItemPublic
from app.services.auth_service import get_current_active_user

router = APIRouter(tags=["menu_items"])

@router.post("/menu-items",response_model= MenuItemPublic)
def create_menu_item(menu: MenuItemCreate, session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    db_menu_item= MenuItem.model_validate(menu)
    db_menu_item.restaurant_id = current_user.restaurant_id
    session.add(db_menu_item)
    session.commit()
    session.refresh(db_menu_item)
    return db_menu_item

@router.patch("/menu-items/{menu_item_id}" ,response_model= MenuItemPublic)
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
def delete_menu_item(menu_item_id: int, session: SessionDep):
    menu= session.get(MenuItem, menu_item_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu item not found")
    session.delete(menu)
    session.commit()
    return menu

@router.get("/menu-items/{menu_item_id}")
def read_menu_item(menu_item_id: int, session: SessionDep) -> MenuItemPublic:
    menu= session.get(MenuItem, menu_item_id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return menu

@router.get("/menu-items", response_model= List[MenuItemPublic], deprecated= True)
def read_menus_item(session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    statement = (
        select(MenuItem)
        .where(MenuItem.restaurant_id == current_user.restaurant_id)
    )
    results = session.exec(statement).all()
    return results

@router.get("/menu-items-order")
def read_order_menu_item(menus: Annotated[List[MenuItemPublic], Depends(read_menus_item)]):
    return [OrderMenuItemPublic(menu_item=menu,quantity=0, unit_price=menu.price) for menu in menus]

@router.get("/categories/{category_id}/menu-items")
def read_menus_item_by_id_category(category_id: int, session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    menu_db = session.exec(select(MenuItem).where(MenuItem.category_id == category_id, MenuItem.restaurant_id == current_user.restaurant_id)).all()
    return menu_db

###With pics

class MenuCreateItemForm(BaseModel):
    name: str= Field(),
    description: Optional[str] = None,
    price: float = Field(..., gt=0),
    category_id: Optional[int] = Field(None),
    picture: Optional[UploadFile] = Field(None),

def parse_int_list(value: str = Form(...)) -> List[int]:
    try:
        return [int(x.strip()) for x in value.split(',') if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid format. Use comma-separated integers.")

@router.post("/menu-items-pics", response_model=MenuItemPublic)
async def create_menu_item_with_pics(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str = Form(...),
    description: Optional[str] = Form(None),
    price: float = Form(..., gt=0),
    category_id: Optional[int] = Form(None),
    menu_ids: str= Form(...),
    picture: Optional[UploadFile] = File(None),
    #pictures: Optional[List[UploadFile]] = File(None),
):
    # Validate file types if files are provided
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    max_file_size = 10 * 1024 * 1024  # 10MB
    
    picture_url = None
    picture_urls = []
    
    # Handle single picture upload
    if picture:
        if not _is_valid_image(picture, allowed_extensions, max_file_size):
            raise HTTPException(status_code=400, detail="Invalid image file")
        picture_url = await _save_uploaded_file(picture, "menu_items")
    
    # Handle multiple pictures upload
    """
    if pictures:
        for pic in pictures:
            if not _is_valid_image(pic, allowed_extensions, max_file_size):
                raise HTTPException(status_code=400, detail="One or more image files are invalid")
            pic_url = await _save_uploaded_file(pic, "menu_items")
            picture_urls.append(pic_url)
    """

    
    # Create menu item data
    menu_item_data = MenuItemCreate(
        name=name,
        description=description,
        price=price,
        picture=picture_url,
        pictures=picture_urls,
        category_id=category_id
    )
    db_menu_item = MenuItem.model_validate(menu_item_data)
    db_menu_item.menus= session.exec(select(Menu).where(Menu.id.in_([int(x.strip()) for x in menu_ids.split(',') if x.strip()]))).all()
    db_menu_item.restaurant_id = current_user.restaurant_id
    
    session.add(db_menu_item)
    session.commit()
    session.refresh(db_menu_item)
    
    return db_menu_item


# Helper functions for file handling
def _is_valid_image(file: UploadFile, allowed_extensions: set, max_size: int) -> bool:
    """Validate uploaded image file"""
    if not file.filename:
        return False
    
    # Check file extension
    file_ext = PathLib(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        return False
    
    # Check file size (if available)
    if hasattr(file, 'size') and file.size and file.size > max_size:
        return False
    
    return True


async def _save_uploaded_file(file: UploadFile, folder: str) -> str:
    """Save uploaded file and return the file path"""
    # Create upload directory if it doesn't exist
    upload_dir = PathLib(f"uploads/{folder}")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    file_ext = PathLib(file.filename).suffix.lower()
    unique_filename = f"{uuid4()}{file_ext}"
    file_path = upload_dir / unique_filename
    
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    finally:
        file.file.close()
    
    # Return relative path for database storage
    return str(file_path)

