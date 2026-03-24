from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.cores.permissions import require_permission
from app.models.models import Category, CategoryTranslation, User
from app.schemas.category_schemas import CategoryBase, CategoryCreate, CategoryPublic, CategoryUpdate
from app.services.auth_service import get_current_active_user
from app.translations.entity_with_translation_creator import EntityWithTranslationsManager


router = APIRouter(
    tags=["categories"],
    dependencies=[Depends(get_current_active_user)])

@router.post("/categories", response_model=CategoryPublic, dependencies=[require_permission("menu", "create")])
def create_category(category: CategoryCreate, session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    manager = EntityWithTranslationsManager(session, current_user.restaurant_id)
    return manager.create(
        create_data=category,
        main_model=Category,
        translation_model=CategoryTranslation,
        foreign_key_field="category_id"
    )

@router.patch("/categories/{category_id}", response_model=CategoryPublic, dependencies=[require_permission("menu", "update")])
def update_category(category_id: int, category: CategoryUpdate, session: SessionDep):
    manager = EntityWithTranslationsManager(session)
    return manager.update(
        entity_id=category_id,
        update_data=category,
        main_model=Category,
        translation_model=CategoryTranslation,
        foreign_key_field="category_id",
        entity_name="Category"
    )

@router.delete("/categories/{category_id}", dependencies=[require_permission("menu", "delete")])
def delete_category(category_id: int, session: SessionDep):
    category= session.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    session.delete(category)
    session.commit()
    return category.id


@router.get("/categories/{category_id}", response_model=CategoryPublic)
def read_category(category_id: int, session: SessionDep) -> CategoryBase:
    try:
        category= session.get(Category, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        return category
    except  HTTPException as httpexp:
        raise httpexp
    except Exception as exp:
        raise HTTPException(status_code=500, detail=f"{str(exp)}")
    

@router.get("/categories", response_model=List[CategoryPublic], dependencies=[require_permission("menu", "read")])
def read_categories(session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    category_db = session.exec(select(Category).where(Category.restaurant_id == current_user.restaurant_id)).all()
    return category_db

@router.get("/restaurants/{restaurant_id}/categories")
def get_categories_by_restaurant(restaurant_id: int,session: SessionDep):
    category_db = session.exec(select(Category).where(Category.restaurant_id == restaurant_id)).all()
    return category_db