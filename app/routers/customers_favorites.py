from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.models.models import Customer, Favorite, Restaurant
from app.schemas.favorite_schemas import FavoriteCreate, FavoritePublic
from app.services.customer_auth_service import get_current_customer


router = APIRouter(prefix="/customers/me/favorites", tags=["customers"])


@router.get("", response_model=list[FavoritePublic])
def list_favorites(
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Favorite]:
    statement = (
        select(Favorite)
        .where(Favorite.customer_id == current.id)
        .order_by(Favorite.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return session.exec(statement).all()


@router.post("", response_model=FavoritePublic)
def add_favorite(
    payload: FavoriteCreate,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> Favorite:
    # Restaurant must exist and not be disabled — same visibility rule as the
    # public endpoints.
    restaurant = session.get(Restaurant, payload.restaurant_id)
    if restaurant is None or restaurant.disabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found",
        )

    # Idempotent: if the favorite already exists, return it instead of 409.
    existing = session.exec(
        select(Favorite).where(
            Favorite.customer_id == current.id,
            Favorite.restaurant_id == payload.restaurant_id,
        )
    ).first()
    if existing is not None:
        return existing

    favorite = Favorite(customer_id=current.id, restaurant_id=payload.restaurant_id)
    session.add(favorite)
    try:
        session.commit()
    except IntegrityError:
        # Race: another request inserted concurrently. Fetch and return.
        session.rollback()
        favorite = session.exec(
            select(Favorite).where(
                Favorite.customer_id == current.id,
                Favorite.restaurant_id == payload.restaurant_id,
            )
        ).first()
        if favorite is None:
            raise
        return favorite
    session.refresh(favorite)
    return favorite


@router.delete("/{restaurant_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(
    restaurant_id: int,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> None:
    favorite = session.exec(
        select(Favorite).where(
            Favorite.customer_id == current.id,
            Favorite.restaurant_id == restaurant_id,
        )
    ).first()
    if favorite is None:
        # Per the plan: DELETE removes only the caller's row, never another's.
        # If nothing to delete, return 204 idempotently rather than 404.
        return None
    session.delete(favorite)
    session.commit()
    return None
