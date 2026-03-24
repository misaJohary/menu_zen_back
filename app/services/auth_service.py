from datetime import datetime, timedelta, timezone
from typing import Annotated, Union
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy import Result, select
from sqlmodel import Session

from app.configs.auth_configs import settings
from app.configs.database_configs import engine

import jwt

from app.models.models import Role, User
from app.schemas.auth_schemas import RoleName, TokenData, UserBase, UserPublic

def get_role_id_by_name(role_name: str, session: Session) -> int:
    """Resolve a role name to its numerical ID."""
    # Use scalars() to ensure we get the Role object itself, not a Row
    role = session.exec(select(Role).where(Role.name == role_name)).first()
    
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_name}' not found",
        )
    
    # In some versions of SQLModel/SQLAlchemy, .first() on exec() might return a Row
    # if not properly wrapped. We'll access it safely.
    if hasattr(role, "id"):
        return role.id
    
    # Fallback if it's a row-like object where the entity is the first element
    return role[0].id

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(username: str) -> User:
    with Session(engine) as session:
        result: Result = session.exec(select(User).where(User.username == username))
        user = result.scalar()
        return user
    
def get_user_by_id(id: int) -> User:
    with Session(engine) as session:
        result: Result = session.get(User, id)
        return result
    
async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code= status.HTTP_401_UNAUTHORIZED,
        detail= "Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload= jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm], options={"verify_sub": False} ) 
        user_id= payload.get("user_id")
        if user_id is None:
            raise credentials_exception
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise credentials_exception

    except Exception as e:
        print(f"Unexpected error: {e}")
        raise credentials_exception
    user = get_user_by_id(user_id)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: Annotated[UserPublic, Depends(get_current_user)]):
    #if current_user.disabled:
        #raise HTTPException(status_code= 400, detail= "Inactive User")
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
    
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
        to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt