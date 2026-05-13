from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.models.models import Customer, Restaurant, RestaurantReview
from app.schemas.review_schemas import (
    ReviewCreate,
    ReviewCustomer,
    ReviewPublic,
    ReviewUpdate,
)
from app.services.customer_auth_service import get_current_customer


router = APIRouter(prefix="/customers/me/reviews", tags=["customers"])


def _to_public(review: RestaurantReview, customer: Customer) -> ReviewPublic:
    return ReviewPublic(
        id=review.id,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
        customer=ReviewCustomer(
            id=customer.id,
            display_name=customer.full_name,
            avatar=customer.avatar,
        ),
    )


@router.post("", response_model=ReviewPublic, status_code=status.HTTP_201_CREATED)
def create_review(
    payload: ReviewCreate,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> ReviewPublic:
    restaurant = session.get(Restaurant, payload.restaurant_id)
    if restaurant is None or restaurant.disabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found",
        )

    review = RestaurantReview(
        customer_id=current.id,
        restaurant_id=payload.restaurant_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    session.add(review)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already reviewed this restaurant",
        )
    session.refresh(review)
    return _to_public(review, current)


@router.get("", response_model=list[ReviewPublic])
def list_my_reviews(
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReviewPublic]:
    statement = (
        select(RestaurantReview)
        .where(RestaurantReview.customer_id == current.id)
        .order_by(RestaurantReview.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = session.exec(statement).all()
    return [_to_public(r, current) for r in rows]


@router.patch("/{review_id}", response_model=ReviewPublic)
def update_review(
    review_id: int,
    payload: ReviewUpdate,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> ReviewPublic:
    review = session.get(RestaurantReview, review_id)
    if review is None or review.customer_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )
    data = payload.model_dump(exclude_unset=True)
    if "rating" in data and data["rating"] is not None:
        review.rating = data["rating"]
    if "comment" in data:
        review.comment = data["comment"]
    review.updated_at = datetime.now()
    session.add(review)
    session.commit()
    session.refresh(review)
    return _to_public(review, current)


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: int,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> None:
    review = session.get(RestaurantReview, review_id)
    if review is None or review.customer_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )
    session.delete(review)
    session.commit()
    return None
