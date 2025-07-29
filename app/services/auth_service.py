from datetime import datetime, timedelta, timezone
from typing import Annotated, Union
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy import Result, select
from sqlmodel import Session

from app.configs.auth_configs import settings
from app.configs.database_configs import engine
from app.models.auth_models import UserDB

import jwt

from app.schemas.auth_schemas import TokenData, User, UserPublic

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(username: str) -> UserDB:
    with Session(engine) as session:
        result: Result = session.exec(select(UserDB).where(UserDB.username == username))
        user = result.scalar()
        return user
    
async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code= status.HTTP_401_UNAUTHORIZED,
        detail= "Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload= jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username= payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data= TokenData(username= username)
    except jwt.InvalidTokenError:
        raise credentials_exception
    user = get_user(token_data.username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: Annotated[UserPublic, Depends(get_current_user)]):
    if current_user.disabled:
        raise HTTPException(status_code= 400, detail= "Inactive User")
    return current_user

def authenticate_user(username: str, password: str) -> User: 
    user = get_user(username)
    #print(user.model_dump())
    if not user:
        return False
    if not verify_password(password, user.hashed_psd):
        return False
    return user

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt