from typing import Annotated, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.configs.database_configs import SessionDep
from app.models.models import (
    Category,
    Customer,
    Menu,
    MenuItem,
    MenuItemTranslation,
    Restaurant,
    RestaurantReview,
)
from app.schemas.category_schemas import CategoryPublic
from app.schemas.menu_item_schemas import MenuItemPublic
from app.schemas.menu_schemas import MenuPublic
from app.schemas.restaurant_schemas import RestaurantPublic, RestaurantType
from app.schemas.review_schemas import ReviewCustomer, ReviewPublic, ReviewSummary
from app.services.geo_service import nearby_restaurants_query


def _get_visible_restaurant(session: Session, restaurant_id: int) -> Restaurant:
    restaurant = session.get(Restaurant, restaurant_id)
    if restaurant is None or restaurant.disabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found",
        )
    return restaurant


def _review_aggregate(session: Session, restaurant_id: int) -> tuple[Optional[float], int]:
    row = session.exec(
        select(
            func.avg(RestaurantReview.rating),
            func.count(RestaurantReview.id),
        ).where(RestaurantReview.restaurant_id == restaurant_id)
    ).one()
    avg = row[0] if hasattr(row, "__getitem__") else None
    count = row[1] if hasattr(row, "__getitem__") else 0
    return (float(avg) if avg is not None else None), int(count or 0)


router = APIRouter(prefix="/public", tags=["public"])


class RestaurantSearchItem(RestaurantPublic):
    distance_km: Optional[float] = None


class RestaurantSearchResponse(BaseModel):
    total: int
    items: list[RestaurantSearchItem]


class RestaurantDetailPublic(RestaurantPublic):
    avg_rating: Optional[float] = None
    review_count: int = 0


@router.get("/restaurants/search", response_model=RestaurantSearchResponse)
def search_restaurants(
    session: SessionDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    long: Annotated[float, Query(ge=-180, le=180)],
    radius_km: Annotated[Optional[float], Query(gt=0, le=500)] = None,
    q: Annotated[Optional[str], Query(max_length=120)] = None,
    type: Annotated[Optional[RestaurantType], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RestaurantSearchResponse:
    rows, total = nearby_restaurants_query(
        session=session,
        lat=lat,
        long=long,
        radius_km=radius_km,
        q=q,
        type_=type.value if type is not None else None,
        limit=limit,
        offset=offset,
    )
    items: list[RestaurantSearchItem] = []
    for restaurant, distance_km in rows:
        data = RestaurantPublic.model_validate(restaurant, from_attributes=True).model_dump()
        data["distance_km"] = (
            round(distance_km, 2) if distance_km is not None else None
        )
        items.append(RestaurantSearchItem(**data))
    return RestaurantSearchResponse(total=total, items=items)


@router.get("/restaurants/{restaurant_id}", response_model=RestaurantDetailPublic)
def get_restaurant_public(
    restaurant_id: int,
    session: SessionDep,
) -> RestaurantDetailPublic:
    restaurant = _get_visible_restaurant(session, restaurant_id)
    data = RestaurantPublic.model_validate(restaurant, from_attributes=True).model_dump()
    avg_rating, review_count = _review_aggregate(session, restaurant_id)
    return RestaurantDetailPublic(
        **data,
        avg_rating=round(avg_rating, 2) if avg_rating is not None else None,
        review_count=review_count,
    )


@router.get("/restaurants/{restaurant_id}/menus", response_model=list[MenuPublic])
def list_restaurant_menus(
    restaurant_id: int,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Menu]:
    _get_visible_restaurant(session, restaurant_id)
    statement = (
        select(Menu)
        .where(Menu.restaurant_id == restaurant_id, Menu.active == True)  # noqa: E712
        .offset(offset)
        .limit(limit)
    )
    return session.exec(statement).all()


@router.get("/restaurants/{restaurant_id}/categories", response_model=list[CategoryPublic])
def list_restaurant_categories(
    restaurant_id: int,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Category]:
    _get_visible_restaurant(session, restaurant_id)
    statement = (
        select(Category)
        .where(
            Category.restaurant_id == restaurant_id,
            Category.active == True,  # noqa: E712
        )
        .offset(offset)
        .limit(limit)
    )
    return session.exec(statement).all()


@router.get("/restaurants/{restaurant_id}/menu-items", response_model=list[MenuItemPublic])
def list_restaurant_menu_items(
    restaurant_id: int,
    session: SessionDep,
    menu_id: Annotated[Optional[int], Query()] = None,
    category_id: Annotated[Optional[int], Query()] = None,
    search: Annotated[Optional[str], Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MenuItem]:
    _get_visible_restaurant(session, restaurant_id)
    statement = select(MenuItem).where(
        MenuItem.restaurant_id == restaurant_id,
        MenuItem.active == True,  # noqa: E712
    )
    if category_id is not None:
        statement = statement.where(MenuItem.category_id == category_id)
    if menu_id is not None:
        statement = statement.where(MenuItem.menus.any(Menu.id == menu_id))
    if search:
        like = f"%{search}%"
        statement = statement.where(
            MenuItem.translations.any(MenuItemTranslation.name.ilike(like))
        )
    statement = statement.offset(offset).limit(limit)
    return session.exec(statement).all()


@router.get("/menu-items/{menu_item_id}", response_model=MenuItemPublic)
def get_public_menu_item(
    menu_item_id: int,
    session: SessionDep,
) -> MenuItem:
    item = session.get(MenuItem, menu_item_id)
    if item is None or not item.active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found",
        )
    # Also hide items whose restaurant is disabled.
    if item.restaurant is not None and item.restaurant.disabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found",
        )
    return item


@router.get("/restaurants/{restaurant_id}/reviews", response_model=list[ReviewPublic])
def list_restaurant_reviews(
    restaurant_id: int,
    session: SessionDep,
    sort: Annotated[Literal["recent", "top", "low"], Query()] = "recent",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReviewPublic]:
    _get_visible_restaurant(session, restaurant_id)
    statement = (
        select(RestaurantReview, Customer)
        .join(Customer, Customer.id == RestaurantReview.customer_id)
        .where(RestaurantReview.restaurant_id == restaurant_id)
    )
    if sort == "top":
        statement = statement.order_by(
            RestaurantReview.rating.desc(),
            RestaurantReview.created_at.desc(),
        )
    elif sort == "low":
        statement = statement.order_by(
            RestaurantReview.rating.asc(),
            RestaurantReview.created_at.desc(),
        )
    else:
        statement = statement.order_by(RestaurantReview.created_at.desc())
    statement = statement.offset(offset).limit(limit)

    rows = session.exec(statement).all()
    return [
        ReviewPublic(
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
        for review, customer in rows
    ]


@router.get(
    "/restaurants/{restaurant_id}/reviews/summary",
    response_model=ReviewSummary,
)
def get_review_summary(
    restaurant_id: int,
    session: SessionDep,
) -> ReviewSummary:
    _get_visible_restaurant(session, restaurant_id)
    avg_rating, count = _review_aggregate(session, restaurant_id)

    histogram = {i: 0 for i in range(1, 6)}
    if count > 0:
        bucket_rows = session.exec(
            select(RestaurantReview.rating, func.count(RestaurantReview.id))
            .where(RestaurantReview.restaurant_id == restaurant_id)
            .group_by(RestaurantReview.rating)
        ).all()
        for rating, bucket_count in bucket_rows:
            if rating is not None and 1 <= int(rating) <= 5:
                histogram[int(rating)] = int(bucket_count)

    return ReviewSummary(
        avg=round(avg_rating, 2) if avg_rating is not None else None,
        count=count,
        histogram=histogram,
    )
