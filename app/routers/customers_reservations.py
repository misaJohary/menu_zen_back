from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.models.models import (
    Customer,
    Reservation,
    Restaurant,
    TableReservation,
)
from app.schemas.reservation_schemas import (
    CustomerReservationCreate,
    CustomerReservationPublic,
    TableAssignmentPublic,
)
from app.schemas.restaurant_schemas import RestaurantPublic
from app.schemas.restaurant_table_schemas import ReservationStatus
from app.services.customer_auth_service import get_current_customer


router = APIRouter(prefix="/customers/me/reservations", tags=["customers"])


def _to_public(reservation: Reservation) -> CustomerReservationPublic:
    assignments = [
        TableAssignmentPublic(id=tr.id, table_id=tr.table_id, status=tr.status)
        for tr in (reservation.table_reservations or [])
    ]
    return CustomerReservationPublic(
        id=reservation.id,
        reserved_at=reservation.reserved_at,
        status=reservation.status,
        party_size=reservation.party_size,
        note=reservation.note,
        created_at=reservation.created_at,
        restaurant=RestaurantPublic.model_validate(
            reservation.restaurant, from_attributes=True
        ),
        assigned_tables=assignments,
    )


@router.post("", response_model=CustomerReservationPublic, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: CustomerReservationCreate,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> CustomerReservationPublic:
    restaurant = session.get(Restaurant, payload.restaurant_id)
    if restaurant is None or restaurant.disabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found",
        )

    # Copy name and phone from the customer profile so staff still see them
    # alongside legacy staff-created reservations.
    name = current.full_name or current.email
    phone = current.phone or ""

    reservation = Reservation(
        name=name,
        phone=phone,
        reserved_at=payload.reserved_at,
        status=ReservationStatus.ACTIVE,
        note=payload.note,
        customer_id=current.id,
        restaurant_id=payload.restaurant_id,
        party_size=payload.party_size,
    )
    session.add(reservation)
    session.commit()
    session.refresh(reservation)
    return _to_public(reservation)


@router.get("", response_model=list[CustomerReservationPublic])
def list_my_reservations(
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
    status_filter: Annotated[
        Optional[ReservationStatus],
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CustomerReservationPublic]:
    statement = (
        select(Reservation)
        .where(Reservation.customer_id == current.id)
        .order_by(Reservation.reserved_at.desc())
    )
    if status_filter is not None:
        statement = statement.where(Reservation.status == status_filter)
    statement = statement.offset(offset).limit(limit)
    rows = session.exec(statement).all()
    return [_to_public(r) for r in rows]


@router.get("/{reservation_id}", response_model=CustomerReservationPublic)
def get_my_reservation(
    reservation_id: int,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> CustomerReservationPublic:
    reservation = session.get(Reservation, reservation_id)
    if reservation is None or reservation.customer_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )
    return _to_public(reservation)


@router.patch("/{reservation_id}/cancel", response_model=CustomerReservationPublic)
def cancel_my_reservation(
    reservation_id: int,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> CustomerReservationPublic:
    reservation = session.get(Reservation, reservation_id)
    if reservation is None or reservation.customer_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )
    if reservation.status == ReservationStatus.CANCELLED:
        return _to_public(reservation)
    if reservation.status not in {ReservationStatus.ACTIVE}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel reservation in status '{reservation.status}'",
        )

    reservation.status = ReservationStatus.CANCELLED
    reservation.updated_at = datetime.now()
    session.add(reservation)

    # Cascade cancellation to any existing table assignments.
    for tr in reservation.table_reservations or []:
        tr.status = ReservationStatus.CANCELLED
        tr.updated_at = datetime.now()
        session.add(tr)

    session.commit()
    session.refresh(reservation)
    return _to_public(reservation)
