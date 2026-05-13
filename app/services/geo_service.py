from typing import Optional

from sqlalchemy import Float, Integer, and_, cast, func, literal_column, select
from sqlmodel import Session

from app.models.models import Restaurant


def make_point(lat: float, long: float):
    """SQLAlchemy expression returning a geography point for (lat, long).

    Note: PostGIS ST_MakePoint takes (X=longitude, Y=latitude).
    """
    return func.ST_SetSRID(func.ST_MakePoint(long, lat), 4326).cast(
        Restaurant.__table__.c.location.type
    )


def nearby_restaurants_query(
    session: Session,
    lat: float,
    long: float,
    radius_km: Optional[float] = None,
    q: Optional[str] = None,
    type_: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[tuple[Restaurant, float]], int]:
    """Return (rows, total_count) for nearby restaurants.

    Each row is `(Restaurant, distance_km)`, ordered by distance ascending.
    Disabled or unlocated restaurants are excluded.
    """
    point = make_point(lat, long)
    distance_m = func.ST_Distance(Restaurant.location, point)
    distance_km = cast(distance_m / 1000.0, Float)

    filters = [Restaurant.location.is_not(None), Restaurant.disabled == False]  # noqa: E712
    if radius_km is not None:
        filters.append(func.ST_DWithin(Restaurant.location, point, radius_km * 1000.0))
    if q:
        like = f"%{q}%"
        filters.append(Restaurant.name.ilike(like))
    if type_:
        filters.append(Restaurant.type == type_)

    base = select(Restaurant, distance_km.label("distance_km")).where(and_(*filters))

    total_row = session.exec(
        select(func.count()).select_from(base.subquery())
    ).one()
    total = total_row[0] if hasattr(total_row, "__getitem__") else total_row

    rows = session.exec(
        base.order_by(distance_m.asc()).offset(offset).limit(limit)
    ).all()

    result: list[tuple[Restaurant, float]] = []
    for row in rows:
        restaurant = row[0]
        dist = row[1]
        result.append((restaurant, float(dist) if dist is not None else None))
    return result, int(total)
