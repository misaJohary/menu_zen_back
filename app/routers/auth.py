from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated


from fastapi import Depends, HTTPException, Query, status, APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.configs.auth_configs import settings
from app.configs.database_configs import SessionDep
from app.cores.permissions import require_permission
from app.models.models import Restaurant, User, Role
from app.services.auth_service import authenticate_user, create_access_token, get_current_active_user, get_password_hash, get_role_id_by_name
from app.schemas.auth_schemas import RoleName, Token, UserCreate, UserPublic, UserRestaurant, UserUpdate
from app.services.permission_service import _load_role_name

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


@router.post("/users", response_model=UserPublic, dependencies=[require_permission("users", "create")])
def create_user(
    user: UserCreate, 
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    # Determine the role_id: 
    # 1. Use role_id if provided.
    # 2. Use role_name if provided.
    # 3. Default to "admin".
    role_id = user.role_id
    if not role_id:
        role_name = user.role_name or RoleName.ADMIN
        role_id = get_role_id_by_name(role_name, session)
        
    db_user = User(
        **user.model_dump(exclude={'password', 'role_name', 'role_id', 'restaurant_id'}),
        hashed_psd=get_password_hash(user.password),
        role_id=role_id,
        restaurant_id=user.restaurant_id or current_user.restaurant_id
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@router.get("/user", response_model=UserRestaurant)
def get_user_restaurant(session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    db_restaurant = None
    if current_user.restaurant_id:
        db_restaurant = session.get(Restaurant, current_user.restaurant_id)
        
    db_user = session.get(User, current_user.id)
    return UserRestaurant(
        user=db_user,
        restaurant=db_restaurant
    )


@router.get("/users/", response_model=list[UserPublic], dependencies=[require_permission("users", "read")])
def get_users(session: SessionDep, offset: int=0, limit: Annotated[int, Query(le=100)]=100):
    users_db = session.exec(select(User).offset(offset).limit(limit)).scalars().all()
    return users_db

@router.get("/users/{user_id}", response_model=UserPublic, dependencies=[require_permission("users", "read")])
def get_user_by_id_endpoint(user_id: int, session: SessionDep):
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user

@router.patch("/user", response_model=UserPublic)
def update_current_user(
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
    
    # Special handling for role_name
    if "role_name" in update_data:
        role_name = update_data.pop("role_name")
        update_data["role_id"] = get_role_id_by_name(role_name, session)

    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@router.patch("/users/{user_id}", response_model=UserPublic, dependencies=[require_permission("users", "update")])
def update_user(
    user_id: int,
    user_update: UserUpdate,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    """Update another user (Admin only)"""
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # Prevent updating a user from another restaurant if not super_admin
    # First, get current user role name
    caller_role_name = _load_role_name(current_user, session)
    
    if caller_role_name != "super_admin":
        if db_user.restaurant_id != current_user.restaurant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify users from other restaurants")
    
    update_data = user_update.model_dump(exclude_unset=True)
    
    # Handling role_name resolution
    if "role_name" in update_data:
        role_name = update_data.pop("role_name")
        update_data["role_id"] = get_role_id_by_name(role_name, session)

    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[require_permission("users", "delete")])
def delete_user(
    user_id: int,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    """Delete a user (Admin only)"""
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    caller_role_name = _load_role_name(current_user, session)
    
    if caller_role_name != "super_admin":
        if db_user.restaurant_id != current_user.restaurant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete users from other restaurants")
            
    session.delete(db_user)
    session.commit()
    return None