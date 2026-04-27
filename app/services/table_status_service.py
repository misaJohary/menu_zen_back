from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks
from sqlalchemy import and_ as sa_and
from sqlmodel import Session, exists, select

from app.models.models import (
    Order,
    Reservation,
    RestaurantTable,
    TableReservation,
    TableStatusLog,
    User,
)
from app.schemas.auth_schemas import RoleName
from app.schemas.order_shemas import OrderStatus, PaymentStatus
from app.schemas.restaurant_table_schemas import ReservationStatus, TableStatus
from app.services import permission_service
from app.services.ws_service import ConnectionManager


TERMINAL_RESERVATION_STATUSES = {
    ReservationStatus.HONORED,
    ReservationStatus.CANCELLED,
    ReservationStatus.NO_SHOW,
}


_SERVER_LIKE_ROLES = {
    RoleName.SERVER.value,
    RoleName.ADMIN.value,
    RoleName.SUPER_ADMIN.value,
}


def is_server_like(role_name: str) -> bool:
    return role_name in _SERVER_LIKE_ROLES


def active_table_reservation(session: Session, table_id: int) -> Optional[TableReservation]:
    return session.exec(
        select(TableReservation)
        .where(TableReservation.table_id == table_id)
        .where(TableReservation.status == ReservationStatus.ACTIVE)
    ).first()


def _current_occupancy_started_at(session: Session, table_id: int) -> datetime:
    """Return the timestamp at which the table most recently left `free`.

    Used to scope auto-release checks to the current occupancy so that stale
    `unpaid` orders from previous services cannot block release. Falls back to
    `datetime.min` when the table has no qualifying log entry (e.g. table that
    has never been claimed since the log was introduced) — in that case any
    open order will still block release, which is the safe default.
    """
    row = session.exec(
        select(TableStatusLog.changed_at)
        .where(TableStatusLog.table_id == table_id)
        .where(TableStatusLog.old_status == TableStatus.FREE)
        .where(TableStatusLog.new_status != TableStatus.FREE)
        .order_by(TableStatusLog.changed_at.desc())
    ).first()
    return row if row is not None else datetime.min


def cascade_parent_reservation_status(
    session: Session,
    reservation_id: int,
) -> None:
    """If every TableReservation for a parent Reservation is terminal, update
    the parent's status to match (all-honored → honored, etc.)."""
    rows = session.exec(
        select(TableReservation).where(TableReservation.reservation_id == reservation_id)
    ).all()
    if not rows:
        return
    statuses = {row.status for row in rows}
    if not statuses.issubset(TERMINAL_RESERVATION_STATUSES):
        return
    if len(statuses) == 1:
        new_status = next(iter(statuses))
    elif ReservationStatus.HONORED in statuses:
        new_status = ReservationStatus.HONORED
    elif ReservationStatus.CANCELLED in statuses:
        new_status = ReservationStatus.CANCELLED
    else:
        new_status = ReservationStatus.NO_SHOW

    parent = session.get(Reservation, reservation_id)
    if parent is not None and parent.status != new_status:
        parent.status = new_status
        parent.updated_at = datetime.now()
        session.add(parent)


def build_status_broadcast(
    table: RestaurantTable,
    old_status: TableStatus,
    changed_by_id: Optional[int],
    active: Optional[TableReservation],
) -> dict:
    reserved_at = None
    if active is not None and active.reservation is not None:
        reserved_at = active.reservation.reserved_at.isoformat()
    return {
        "type": "table_status_changed",
        "table_id": table.id,
        "table_name": table.name,
        "old_status": old_status,
        "new_status": table.status,
        "server_id": table.server_id,
        "waiting_since": table.waiting_since.isoformat() if table.waiting_since else None,
        "reservation_at": reserved_at,
        "changed_by_id": changed_by_id,
        "timestamp": datetime.now().isoformat(),
    }


def maybe_auto_claim_table(
    table_id: int,
    current_user: User,
    session: Session,
    background_tasks: BackgroundTasks,
    manager: ConnectionManager,
) -> None:
    """Claim a table when an order is created on it.

    Transition matrix:
      free      + server-like  → assigned (server_id = creator)
      free      + other        → waiting  (waiting_since = now)
      reserved  + server-like  → assigned + cascade active TableReservation → honored
      reserved  + other        → waiting  + cascade active TableReservation → honored
      waiting   + server-like  → assigned (clear waiting_since)
      waiting   + other        → no-op
      assigned  + anyone       → no-op (never reassign implicitly)
    """
    table = session.get(RestaurantTable, table_id)
    if table is None:
        return
    if table.restaurant_id != current_user.restaurant_id:
        return

    role_name = permission_service._load_role_name(current_user, session)
    server_like = role_name is not None and is_server_like(role_name)

    old_status = table.status
    target: Optional[TableStatus] = None

    if old_status == TableStatus.FREE:
        target = TableStatus.ASSIGNED if server_like else TableStatus.WAITING
    elif old_status == TableStatus.RESERVED:
        target = TableStatus.ASSIGNED if server_like else TableStatus.WAITING
    elif old_status == TableStatus.WAITING:
        if server_like:
            target = TableStatus.ASSIGNED
        else:
            return
    else:
        # ASSIGNED — never reassign implicitly.
        return

    parent_reservation_id: Optional[int] = None
    if old_status == TableStatus.RESERVED:
        active = active_table_reservation(session, table.id)
        if active is not None:
            active.status = ReservationStatus.HONORED
            active.updated_at = datetime.now()
            session.add(active)
            parent_reservation_id = active.reservation_id

    if target == TableStatus.ASSIGNED:
        table.server_id = current_user.id
        table.waiting_since = None
    elif target == TableStatus.WAITING:
        table.waiting_since = datetime.now()
        table.server_id = None

    table.status = target
    table.updated_at = datetime.now()
    session.add(table)

    session.add(
        TableStatusLog(
            table_id=table.id,
            changed_by_id=current_user.id,
            old_status=old_status,
            new_status=target,
            note="auto-claimed: order created",
        )
    )

    if parent_reservation_id is not None:
        cascade_parent_reservation_status(session, parent_reservation_id)

    session.commit()
    session.refresh(table)

    refreshed_active = active_table_reservation(session, table.id)
    background_tasks.add_task(
        manager.broadcast_to_restaurant,
        str(table.restaurant_id),
        build_status_broadcast(table, old_status, current_user.id, refreshed_active),
    )


def maybe_auto_release_table(
    table_id: int,
    session: Session,
    background_tasks: BackgroundTasks,
    manager: ConnectionManager,
) -> None:
    """Release a table back to `free` when every order on it is paid (or cancelled).

    Runs a single EXISTS query so cost is independent of order count for the
    table. No-op when the table is already free or still has open orders.
    """
    table = session.get(RestaurantTable, table_id)
    if table is None or table.status == TableStatus.FREE:
        return

    session_start = _current_occupancy_started_at(session, table_id)

    has_open_orders = session.exec(
        select(
            exists().where(
                sa_and(
                    Order.restaurant_table_id == table_id,
                    Order.payment_status != PaymentStatus.PAID,
                    Order.order_status != OrderStatus.CANCELLED,
                    Order.created_at >= session_start,
                )
            )
        )
    ).one()
    if has_open_orders:
        return

    old_status = table.status

    active_reservation = active_table_reservation(session, table_id)
    if active_reservation is not None:
        active_reservation.status = ReservationStatus.CANCELLED
        active_reservation.updated_at = datetime.now()
        session.add(active_reservation)

    table.status = TableStatus.FREE
    table.server_id = None
    table.waiting_since = None
    table.updated_at = datetime.now()
    session.add(table)

    session.add(
        TableStatusLog(
            table_id=table.id,
            changed_by_id=None,
            old_status=old_status,
            new_status=TableStatus.FREE,
            note="auto-released: all orders paid",
        )
    )

    session.commit()
    session.refresh(table)

    background_tasks.add_task(
        manager.broadcast_to_restaurant,
        str(table.restaurant_id),
        {
            "type": "table_status_changed",
            "table_id": table.id,
            "table_name": table.name,
            "old_status": old_status,
            "new_status": table.status,
            "server_id": table.server_id,
            "waiting_since": None,
            "reservation_at": None,
            "changed_by_id": None,
            "timestamp": datetime.now().isoformat(),
        },
    )
