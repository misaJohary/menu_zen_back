from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.configs.database_configs import SessionDep
from app.models.category_models import Category
from app.schemas.category_schemas import CategoryBase, CategoryCreate, CategoryUpdate
from app.services.auth_service import get_current_active_user


router = APIRouter(tags=["categories"], dependencies= [Depends(get_current_active_user)])

@router.post("/categories",response_model= CategoryBase)
def create_category(category: CategoryCreate, session: SessionDep):
    db_cat= Category.model_validate(category)
    session.add(db_cat)
    session.commit()
    session.refresh(db_cat)
    return db_cat

@router.patch("/categories/{category_id}" ,response_model= CategoryBase)
def update_category(category_id: int, category: CategoryUpdate, session: SessionDep):
    category_db = session.get(Category, category_id)
    if not category_db:
        raise HTTPException(status_code=404, detail="Category not found")
    category_data = category.model_dump(exclude_unset=True)
    category_db.sqlmodel_update(category_data)
    session.add(category_db)
    session.commit()
    session.refresh(category_db)
    return category_db

@router.delete("/categories/{category_id}")
def delete_category(category_id: int, session: SessionDep):
    category= session.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    session.delete(category)
    session.commit()
    return {"ok": True}

@router.get("/categories/{category_id}")
def read_category(category_id: int, session: SessionDep) -> CategoryBase:
    category= session.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category

@router.get("/categories")
def read_categories(session: SessionDep):
    category_db = session.exec(select(Category)).scalars().all()
    return category_db