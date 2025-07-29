from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.configs.database_configs import SessionDep
from app.models.category_models import CategoryDB
from app.schemas.category_schemas import Category, CategoryCreate, CategoryUpdate
from app.services.auth_service import get_current_active_user


router = APIRouter(tags=["category"], dependencies= [Depends(get_current_active_user)])

@router.post("/category",response_model= Category)
def create_category(category: CategoryCreate, session: SessionDep):
    db_cat= CategoryDB.model_validate(category)
    session.add(db_cat)
    session.commit()
    session.refresh(db_cat)
    return db_cat

@router.patch("/category/{category_id}" ,response_model= Category)
def update_category(category_id: int, category: CategoryUpdate, session: SessionDep):
    category_db = session.get(CategoryDB, category_id)
    if not category_db:
        raise HTTPException(status_code=404, detail="Category not found")
    category_data = category.model_dump(exclude_unset=True)
    category_db.sqlmodel_update(category_data)
    session.add(category_db)
    session.commit()
    session.refresh(category_db)
    return category_db

@router.delete("/category/{category_id}")
def delete_category(category_id: int, session: SessionDep):
    category= session.get(CategoryDB, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    session.delete(category)
    session.commit()
    return {"ok": True}

@router.get("/category/{category_id}")
def read_category(category_id: int, session: SessionDep) -> Category:
    category= session.get(CategoryDB, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category

@router.get("/categories")
def read_categories(session: SessionDep):
    category_db = session.exec(select(CategoryDB)).scalars().all()
    return category_db