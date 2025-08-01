from datetime import timedelta
from fastapi import APIRouter

from app.configs.database_configs import SessionDep
from app.models.models import Restaurant, User
from app.schemas.auth_schemas import Token, UserCreate, UserPublic, UserRestaurant
from app.schemas.restaurant_schemas import RestaurantCreate
from app.services.auth_service import create_access_token, get_password_hash

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

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)

    session.add(db_user)
    session.commit()
    session.refresh(db_user)

    access_token = create_access_token(
        data={"sub": db_user.id, "restaurant_id": db_restaurant.id}, expires_delta=access_token_expires
    )

    return UserRestaurant(**db_user.model_dump(), restaurant=db_user.restaurant, token=Token(access_token=access_token, token_type="bearer"))