from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.cores.permissions import require_permission
from app.models.models import Reservation, User
from app.schemas.reservation_schemas import (
    StaffReservationPublic,
    TableAssignmentPublic,
)
from app.schemas.restaurant_table_schemas import ReservationStatus
from app.services.auth_service import get_current_active_user


router = APIRouter(prefix="/restaurants/me/reservations", tags=["restaurant-reservations"])


def _to_public(reservation: Reservation) -> StaffReservationPublic:
    assignments = [
        TableAssignmentPublic(id=tr.id, table_id=tr.table_id, status=tr.status)
        for tr in (reservation.table_reservations or [])
    ]
    return StaffReservationPublic(
        id=reservation.id,
        name=reservation.name,
        phone=reservation.phone,
        reserved_at=reservation.reserved_at,
        status=reservation.status,
        party_size=reservation.party_size,
        note=reservation.note,
        customer_id=reservation.customer_id,
        created_at=reservation.created_at,
        updated_at=reservation.updated_at,
        assigned_tables=assignments,
    )


def _load_owned(session, reservation_id: int, restaurant_id: Optional[int]) -> Reservation:
    reservation = session.get(Reservation, reservation_id)
    if reservation is None or reservation.restaurant_id != restaurant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )
    return reservation


@router.get(
    "",
    response_model=list[StaffReservationPublic],
    dependencies=[require_permission("reservations", "manage")],
)
def list_restaurant_reservations(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    status_filter: Annotated[
        Optional[ReservationStatus],
        Query(alias="status"),
    ] = ReservationStatus.WAITING,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StaffReservationPublic]:
    if current_user.restaurant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not attached to a restaurant",
        )
    statement = (
        select(Reservation)
        .where(Reservation.restaurant_id == current_user.restaurant_id)
        .order_by(Reservation.reserved_at.desc())
    )
    if status_filter is not None:
        statement = statement.where(Reservation.status == status_filter)
    statement = statement.offset(offset).limit(limit)
    rows = session.exec(statement).all()
    return [_to_public(r) for r in rows]


def _transition(
    session,
    current_user: User,
    reservation_id: int,
    target: ReservationStatus,
) -> StaffReservationPublic:
    if current_user.restaurant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not attached to a restaurant",
        )
    reservation = _load_owned(session, reservation_id, current_user.restaurant_id)
    if reservation.status != ReservationStatus.WAITING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot {target.value} reservation in status '{reservation.status}'",
        )
    reservation.status = target
    reservation.updated_at = datetime.now()
    session.add(reservation)
    session.commit()
    session.refresh(reservation)
    return _to_public(reservation)


@router.patch(
    "/{reservation_id}/accept",
    response_model=StaffReservationPublic,
    dependencies=[require_permission("reservations", "manage")],
)
def accept_reservation(
    reservation_id: int,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> StaffReservationPublic:
    return _transition(session, current_user, reservation_id, ReservationStatus.ACCEPTED)


@router.patch(
    "/{reservation_id}/refuse",
    response_model=StaffReservationPublic,
    dependencies=[require_permission("reservations", "manage")],
)
def refuse_reservation(
    reservation_id: int,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> StaffReservationPublic:
    return _transition(session, current_user, reservation_id, ReservationStatus.REFUSED)
