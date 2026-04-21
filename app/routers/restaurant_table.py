from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from app.configs.database_configs import SessionDep
from app.cores.permissions import require_permission
from app.models.models import (
    Reservation,
    RestaurantTable,
    TableReservation,
    TableStatusLog,
    User,
)
from app.schemas.auth_schemas import RoleName
from app.schemas.restaurant_table_schemas import (
    ReservationStatus,
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
from app.services.ws_service import ConnectionManager, get_connection_manager


router = APIRouter(tags=["tables"])


# ── Helpers ───────────────────────────────────────────────────────────────────

_TERMINAL_RESERVATION_STATUSES = {
    ReservationStatus.HONORED,
    ReservationStatus.CANCELLED,
    ReservationStatus.NO_SHOW,
}


def _active_table_reservation(session: Session, table_id: int) -> Optional[TableReservation]:
    return session.exec(
        select(TableReservation)
        .where(TableReservation.table_id == table_id)
        .where(TableReservation.status == ReservationStatus.ACTIVE)
    ).first()


def _serialize_table(session: Session, table: RestaurantTable) -> dict:
    """Build the RestaurantTablePublic-shaped dict for a table, including the
    currently-active reservation (if any) and a minimal server summary."""
    active = _active_table_reservation(session, table.id)
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


def _cascade_parent_reservation_status(
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
    if not statuses.issubset(_TERMINAL_RESERVATION_STATUSES):
        return
    # All terminal — if a single terminal status dominates, use it; otherwise
    # prefer HONORED over CANCELLED over NO_SHOW.
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


def _build_status_broadcast(
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
    active = _active_table_reservation(session, table.id)

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
        _cascade_parent_reservation_status(session, parent_reservation_id)

    session.commit()
    session.refresh(table)

    refreshed_active = _active_table_reservation(session, table.id)
    background_tasks.add_task(
        manager.broadcast_to_restaurant,
        str(current_user.restaurant_id),
        _build_status_broadcast(table, old_status, current_user.id, refreshed_active),
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
