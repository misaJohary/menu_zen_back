from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated


from fastapi import Depends, HTTPException, Query, status, APIRouter
from sqlalchemy import select

from app.configs.auth_configs import settings
from app.configs.database_configs import SessionDep
from app.models.auth_models import UserDB
from app.services.auth_service import authenticate_user, create_access_token, get_current_active_user, get_password_hash
from app.schemas.auth_schemas import Token, User, UserCreate, UserPublic

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
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


@router.post("/user", response_model= UserPublic)
def create_user(user: UserCreate, session: SessionDep):
    db_user= UserDB(
        **user.model_dump(exclude={'password'}),
        hashed_psd=get_password_hash(user.password)
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user



@router.get("/users/", response_model=list[UserPublic])
def get_users(session: SessionDep, offset: int=0, limit: Annotated[int, Query(le=100)]=100, _= Depends(get_current_active_user)):
    users_db = session.exec(select(UserDB).offset(offset).limit(limit)).scalars().all()
    return users_db