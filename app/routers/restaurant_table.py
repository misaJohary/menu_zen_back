from datetime import datetime
from typing import Annotated, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from app.configs.database_configs import SessionDep
from app.cores.permissions import require_permission
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
from app.schemas.restaurant_table_schemas import (
    ReservationStatus,
    ResetDailyRequest,
    ResetDailySummary,
    RestaurantTableBase,
    RestaurantTableCreate,
    RestaurantTablePublic,
    RestaurantTableStatusUpdate,
    RestaurantTableUpdate,
    TableStatus,
    TableStatusLogPublic,
)
from app.services import permission_service
from app.services.auth_service import get_current_active_user
from app.services.table_status_service import (
    active_table_reservation,
    build_status_broadcast,
    cascade_parent_reservation_status,
)
from app.services.ws_service import ConnectionManager, get_connection_manager


router = APIRouter(tags=["tables"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _serialize_table(session: Session, table: RestaurantTable) -> dict:
    """Build the RestaurantTablePublic-shaped dict for a table, including the
    currently-active reservation (if any) and a minimal server summary."""
    active = active_table_reservation(session, table.id)
    active_dict = None
    if active is not None:
        reservation = active.reservation
        active_dict = {
            "id": active.id,
            "reservation_id": active.reservation_id,
            "table_id": active.table_id,
            "status": active.status,
            "created_at": active.created_at,
            "updated_at": active.updated_at,
            "reservation": {
                "id": reservation.id,
                "name": reservation.name,
                "phone": reservation.phone,
                "reserved_at": reservation.reserved_at,
                "status": reservation.status,
                "note": reservation.note,
                "created_by_id": reservation.created_by_id,
                "created_at": reservation.created_at,
                "updated_at": reservation.updated_at,
            },
        }

    server_dict = None
    if table.server is not None:
        server_dict = {"id": table.server.id, "username": table.server.username}

    return {
        "id": table.id,
        "name": table.name,
        "restaurant_id": table.restaurant_id,
        "status": table.status,
        "server_id": table.server_id,
        "waiting_since": table.waiting_since,
        "seats": table.seats,
        "server": server_dict,
        "active_reservation": active_dict,
    }


# ── Existing CRUD endpoints ───────────────────────────────────────────────────

@router.post("/tables", dependencies=[require_permission("tables", "manage")])
def create_table(table: RestaurantTableCreate, session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    db_table = RestaurantTable.model_validate(table)
    db_table.restaurant_id = current_user.restaurant_id
    session.add(db_table)
    session.commit()
    session.refresh(db_table)
    return db_table


@router.delete("/tables/{table_id}", dependencies=[require_permission("tables", "manage")])
def delete_table(table_id: int, session: SessionDep):
    table = session.get(RestaurantTable, table_id)
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    session.delete(table)
    session.commit()
    return table.id


@router.patch("/tables/{table_id}", response_model=RestaurantTableBase, dependencies=[require_permission("tables", "manage")])
def update_table(table_id: int, table: RestaurantTableUpdate, session: SessionDep):
    table_db = session.get(RestaurantTable, table_id)
    if not table_db:
        raise HTTPException(status_code=404, detail="Table not found")
    table_data = table.model_dump(exclude_unset=True)

    table_db.sqlmodel_update(table_data)
    session.add(table_db)
    session.commit()
    session.refresh(table_db)
    return table_db


@router.get("/tables", response_model=List[RestaurantTablePublic], dependencies=[require_permission("tables", "read")])
def read_tables(session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    tables = session.exec(
        select(RestaurantTable).where(RestaurantTable.restaurant_id == current_user.restaurant_id)
    ).all()
    return [_serialize_table(session, t) for t in tables]


# ── Status-change endpoint ────────────────────────────────────────────────────

@router.patch("/tables/{table_id}/status", response_model=RestaurantTablePublic)
def change_table_status(
    table_id: int,
    payload: RestaurantTableStatusUpdate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_active_user)],
    manager: ConnectionManager = Depends(get_connection_manager),
):
    table = session.get(RestaurantTable, table_id)
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    if table.restaurant_id != current_user.restaurant_id:
        raise HTTPException(status_code=403, detail="Table belongs to a different restaurant")

    new_status = payload.status
    role_name = permission_service._load_role_name(current_user, session)

    # ── Permission / transition checks ────────────────────────────────────
    if new_status == TableStatus.WAITING:
        # Open to any authenticated user in the same restaurant.
        pass
    elif new_status == TableStatus.RESERVED:
        if role_name not in (RoleName.ADMIN.value, RoleName.SUPER_ADMIN.value):
            raise HTTPException(status_code=403, detail="Only admins can mark a table reserved")
        has_ref = payload.reservation_id is not None
        has_inline = (
            payload.reservation_name is not None
            and payload.reservation_phone is not None
            and payload.reservation_at is not None
        )
        if has_ref == has_inline:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Provide either reservation_id OR all of "
                    "(reservation_name, reservation_phone, reservation_at) — not both"
                ),
            )
    else:
        # assigned / free
        if not permission_service.can(current_user, "tables", "update", session):
            raise HTTPException(status_code=403, detail="Not allowed: tables:update")
        if (
            new_status == TableStatus.ASSIGNED
            and role_name == RoleName.SERVER.value
            and table.status == TableStatus.ASSIGNED
            and table.server_id is not None
            and table.server_id != current_user.id
        ):
            raise HTTPException(
                status_code=403,
                detail="Only the assigned server (or an admin) can reassign this table",
            )

    old_status = table.status

    # ── Apply side effects ────────────────────────────────────────────────
    active = active_table_reservation(session, table.id)

    if old_status == TableStatus.RESERVED and new_status != TableStatus.RESERVED:
        # Transitioning away from reserved — close the active link row.
        if active is not None:
            active.status = (
                ReservationStatus.HONORED
                if new_status in (TableStatus.WAITING, TableStatus.ASSIGNED)
                else ReservationStatus.CANCELLED
            )
            active.updated_at = datetime.now()
            session.add(active)
            parent_reservation_id = active.reservation_id
        else:
            parent_reservation_id = None
    else:
        parent_reservation_id = None

    if new_status == TableStatus.WAITING:
        table.waiting_since = datetime.now()
        table.server_id = None
    elif new_status == TableStatus.ASSIGNED:
        table.server_id = current_user.id
        table.waiting_since = None
    elif new_status == TableStatus.FREE:
        table.server_id = None
        table.waiting_since = None
    elif new_status == TableStatus.RESERVED:
        table.server_id = None
        table.waiting_since = None

        if payload.reservation_id is not None:
            reservation = session.get(Reservation, payload.reservation_id)
            if reservation is None:
                raise HTTPException(status_code=404, detail="Reservation not found")
        else:
            reservation = Reservation(
                name=payload.reservation_name,
                phone=payload.reservation_phone,
                reserved_at=payload.reservation_at,
                note=payload.reservation_note,
                created_by_id=current_user.id,
            )
            session.add(reservation)
            session.flush()

        link = TableReservation(
            reservation_id=reservation.id,
            table_id=table.id,
            status=ReservationStatus.ACTIVE,
        )
        session.add(link)

    table.status = new_status
    table.updated_at = datetime.now()
    session.add(table)

    session.add(
        TableStatusLog(
            table_id=table.id,
            changed_by_id=current_user.id,
            old_status=old_status,
            new_status=new_status,
        )
    )

    if parent_reservation_id is not None:
        cascade_parent_reservation_status(session, parent_reservation_id)

    session.commit()
    session.refresh(table)

    refreshed_active = active_table_reservation(session, table.id)
    background_tasks.add_task(
        manager.broadcast_to_restaurant,
        str(current_user.restaurant_id),
        build_status_broadcast(table, old_status, current_user.id, refreshed_active),
    )

    return _serialize_table(session, table)


# ── Status log endpoint ───────────────────────────────────────────────────────

@router.get(
    "/tables/{table_id}/logs",
    response_model=List[TableStatusLogPublic],
    dependencies=[require_permission("tables", "read")],
)
def read_table_logs(
    table_id: int,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    table = session.get(RestaurantTable, table_id)
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    if table.restaurant_id != current_user.restaurant_id:
        raise HTTPException(status_code=403, detail="Table belongs to a different restaurant")

    return session.exec(
        select(TableStatusLog)
        .where(TableStatusLog.table_id == table_id)
        .order_by(TableStatusLog.changed_at.desc())
    ).all()


# ── Daily reset endpoint ──────────────────────────────────────────────────────

@router.post(
    "/tables/reset-daily",
    response_model=ResetDailySummary,
    dependencies=[require_permission("tables", "reset")],
)
def reset_tables_daily(
    payload: ResetDailyRequest,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_active_user)],
    manager: ConnectionManager = Depends(get_connection_manager),
):
    """Start-of-day reset: free every non-free table, expire stale reservations,
    and close lingering unpaid orders so the next service starts clean.

    Future-dated reservations are intentionally left untouched — a booking for
    tonight must survive a morning reset.
    """
    if current_user.restaurant_id is None:
        raise HTTPException(status_code=400, detail="User is not attached to a restaurant")

    cutoff = payload.cutoff or datetime.now()
    restaurant_id = current_user.restaurant_id

    tables = session.exec(
        select(RestaurantTable).where(RestaurantTable.restaurant_id == restaurant_id)
    ).all()
    table_ids = [t.id for t in tables]

    reservations_expired = 0
    orders_closed = 0

    if table_ids and payload.expire_past_reservations:
        expirable = session.exec(
            select(TableReservation)
            .join(Reservation, Reservation.id == TableReservation.reservation_id)
            .where(TableReservation.table_id.in_(table_ids))
            .where(TableReservation.status == ReservationStatus.ACTIVE)
            .where(Reservation.reserved_at < cutoff)
        ).all()
        affected_parents: set[int] = set()
        for link in expirable:
            link.status = ReservationStatus.NO_SHOW
            link.updated_at = datetime.now()
            session.add(link)
            affected_parents.add(link.reservation_id)
        reservations_expired = len(expirable)
        for parent_id in affected_parents:
            cascade_parent_reservation_status(session, parent_id)

    if table_ids and payload.close_stale_orders:
        stale_orders = session.exec(
            select(Order)
            .where(Order.restaurant_table_id.in_(table_ids))
            .where(Order.payment_status != PaymentStatus.PAID)
            .where(Order.order_status != OrderStatus.CANCELLED)
            .where(Order.created_at < cutoff)
        ).all()
        for order in stale_orders:
            order.order_status = OrderStatus.CANCELLED
            order.updated_at = datetime.now()
            session.add(order)
        orders_closed = len(stale_orders)

    tables_already_free = sum(1 for t in tables if t.status == TableStatus.FREE)
    reset_records: list[tuple[RestaurantTable, TableStatus]] = []
    for table in tables:
        if table.status == TableStatus.FREE:
            continue
        old_status = table.status
        table.status = TableStatus.FREE
        table.server_id = None
        table.waiting_since = None
        table.updated_at = datetime.now()
        session.add(table)
        session.add(
            TableStatusLog(
                table_id=table.id,
                changed_by_id=current_user.id,
                old_status=old_status,
                new_status=TableStatus.FREE,
                note="daily reset",
            )
        )
        reset_records.append((table, old_status))

    session.commit()
    for table, _ in reset_records:
        session.refresh(table)

    summary = ResetDailySummary(
        restaurant_id=restaurant_id,
        tables_reset=len(reset_records),
        tables_already_free=tables_already_free,
        reservations_expired=reservations_expired,
        orders_closed=orders_closed,
        reset_at=datetime.now(),
    )

    for table, old_status in reset_records:
        refreshed_active = active_table_reservation(session, table.id)
        background_tasks.add_task(
            manager.broadcast_to_restaurant,
            str(restaurant_id),
            build_status_broadcast(table, old_status, current_user.id, refreshed_active),
        )

    background_tasks.add_task(
        manager.broadcast_to_restaurant,
        str(restaurant_id),
        {
            "type": "daily_reset",
            "summary": summary.model_dump(mode="json"),
            "timestamp": datetime.now().isoformat(),
        },
    )

    return summary
