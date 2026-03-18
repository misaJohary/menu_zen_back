from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status

from app.configs.database_configs import SessionDep
from app.models.models import Restaurant, User
from app.schemas.auth_schemas import Token, UserCreate, UserPublic, UserRestaurant
from app.schemas.restaurant_schemas import RestaurantCreate, RestaurantUpdate, RestaurantPublic
from app.services.auth_service import create_access_token, get_current_active_user, get_password_hash

from app.configs.auth_configs import settings


router = APIRouter(tags=["restaurants"])

@router.post("/restaurants", response_model=UserRestaurant)
def create_restaurant(restaurant: RestaurantCreate, user: UserCreate, session: SessionDep):
    #create restaurant
    db_restaurant= Restaurant.model_validate(restaurant)

    #create user
    db_user= User(
        **user.model_dump(exclude={'password'}),
        restaurant= db_restaurant,
        hashed_psd=get_password_hash(user.password)
    )

    #access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)

    session.add(db_user)
    session.commit()
    session.refresh(db_user)

    access_token = create_access_token(
        data={"sub": db_user.username, "restaurant_id": db_restaurant.id, "user_id": db_user.id}
    )

    return UserRestaurant(user=db_user.model_dump(), restaurant=db_user.restaurant, token=Token(access_token=access_token, token_type="bearer"))

@router.patch("/restaurant", response_model=RestaurantPublic)
def update_restaurant(
    restaurant_update: RestaurantUpdate,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    """Update the restaurant for the current authenticated user"""
    if not current_user.restaurant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User has no associated restaurant")
    
    db_restaurant = session.get(Restaurant, current_user.restaurant_id)
    if not db_restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    
    # Update only provided fields
    update_data = restaurant_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_restaurant, field, value)
    
    session.add(db_restaurant)
    session.commit()
    session.refresh(db_restaurant)
    return db_restaurant