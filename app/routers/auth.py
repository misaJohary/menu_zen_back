from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated


from fastapi import Depends, HTTPException, Query, status, APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.configs.auth_configs import settings
from app.configs.database_configs import SessionDep
from app.models.models import Restaurant, User
from app.services.auth_service import authenticate_user, create_access_token, get_current_active_user, get_password_hash
from app.schemas.auth_schemas import Token, UserCreate, UserPublic, UserRestaurant, UserUpdate

router = APIRouter(tags=["users"])


@router.post("/login")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    #access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username, "restaurant_id": user.restaurant_id, "user_id": user.id}
    )
    return Token(access_token=access_token, token_type="bearer")


@router.post("/users", response_model= UserPublic)
def create_user(user: UserCreate, session: SessionDep):
    db_user= User(
        **user.model_dump(exclude={'password'}),
        hashed_psd=get_password_hash(user.password)
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@router.get("/user", response_model= UserRestaurant)
def get_user_restaurant(session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    db_restaurant = session.get(Restaurant, current_user.restaurant_id)
    db_user = session.get(User, current_user.id)
    return UserRestaurant(user=db_user.model_dump(), restaurant=db_restaurant.model_dump())



@router.get("/users/", response_model=list[UserPublic])
def get_users(session: SessionDep, offset: int=0, limit: Annotated[int, Query(le=100)]=100):
    users_db = session.exec(select(User).offset(offset).limit(limit)).scalars().all()
    return users_db

@router.patch("/user", response_model=UserPublic)
def update_user(
    user_update: UserUpdate,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    """Update the current authenticated user"""
    db_user = session.get(User, current_user.id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # Update only provided fields
    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user