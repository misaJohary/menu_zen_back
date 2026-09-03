"""Public (guest) dine-in order endpoints.

These endpoints power the QR-scan flow: a customer scans a table QR,
the mobile client resolves the table by name, places an order
without authenticating, and tracks it via a short-lived
`tracking_token`.

See BACKEND_PLAN_ON_PLACE_ORDER.md for the full spec.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy import func
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.enums.order_type import OrderType
from app.models.models import (
    MenuItem,
    Order,
    OrderMenuItem,
    Restaurant,
    RestaurantTable,
)
from app.schemas.order_shemas import (
    CustomerOrderItemPublic,
    CustomerOrderPublic,
    CustomerOrderPublicWithToken,
    OrderStatus,
    PaymentStatus,
    PublicOrderCreate,
    PublicRestaurantTable,
)
from app.services.rate_limit_service import rate_limit
from app.services.ws_service import ConnectionManager, get_connection_manager


router = APIRouter(prefix="/public", tags=["public-orders"])


# Customers can cancel only while the order is still pending — the kitchen
# has not yet started preparing it.
_CANCELLABLE_STATUSES = {OrderStatus.CREATED}

# Sanity cap to catch buggy clients (BACKEND_PLAN §6).
_MAX_TOTAL_AMOUNT = 5_000_000


def _generate_tracking_token() -> str:
    """32 random bytes → ~43-char URL-safe base64 string."""
    return secrets.token_urlsafe(32)


def _to_public(order: Order) -> CustomerOrderPublic:
    items = [
        CustomerOrderItemPublic(
            id=oi.id,
            menu_item_id=oi.menu_item_id,
            quantity=oi.quantity,
            unit_price=oi.unit_price,
            notes=oi.notes,
        )
        for oi in (order.order_menu_items or [])
    ]
    return CustomerOrderPublic(
        id=order.id,
        restaurant_id=order.restaurant_id,
        restaurant_table_id=order.restaurant_table_id,
        restaurant_table_name=order.r_table.name if order.r_table is not None else None,
        order_type=order.order_type,
        order_status=order.order_status,
        payment_status=order.payment_status,
        contact_name=order.contact_name,
        contact_phone=order.contact_phone,
        kitchen_note=order.kitchen_note,
        scheduled_for=order.scheduled_for,
        delivery_address=order.delivery_address,
        delivery_notes=order.delivery_notes,
        total_amount=float(order.total_amount) if order.total_amount is not None else None,
        items=items,
        created_at=order.created_at,
    )


def _load_guest_order(session, order_id: int, token: str) -> Order:
    """Return the order or raise 404 (also when the token is wrong/missing).

    Uses 404 — not 401/403 — so an attacker cannot distinguish
    "order doesn't exist" from "token mismatch".
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    order = session.get(Order, order_id)
    if (
        order is None
        or not order.tracking_token
        or not secrets.compare_digest(order.tracking_token, token)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return order


# ── 4.1  GET /public/restaurants/{id}/tables/by-name/{name} ──────────────────

@router.get(
    "/restaurants/{restaurant_id}/tables/by-name/{table_name}",
    response_model=PublicRestaurantTable,
    dependencies=[Depends(rate_limit("public_tables", per_ip=60))],
)
def get_table_by_name(
    restaurant_id: int,
    table_name: str,
    session: SessionDep,
    response: Response,
) -> PublicRestaurantTable:
    restaurant = session.get(Restaurant, restaurant_id)
    if restaurant is None or restaurant.disabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found",
        )

    table = session.exec(
        select(RestaurantTable).where(
            RestaurantTable.restaurant_id == restaurant_id,
            func.lower(RestaurantTable.name) == table_name.lower(),
        )
    ).first()
    if table is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found",
        )

    response.headers["Cache-Control"] = "public, max-age=60"
    return PublicRestaurantTable(
        id=table.id,
        restaurant_id=table.restaurant_id,
        name=table.name,
        seats=table.seats,
        is_active=True,
    )


# ── 4.2  POST /public/restaurants/{id}/orders ────────────────────────────────

@router.post(
    "/restaurants/{restaurant_id}/orders",
    response_model=CustomerOrderPublicWithToken,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            rate_limit(
                "public_orders_create",
                per_ip=20,
                per_ip_restaurant=5,
            )
        )
    ],
)
def create_guest_order(
    restaurant_id: int,
    payload: PublicOrderCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    manager: Annotated[ConnectionManager, Depends(get_connection_manager)],
) -> CustomerOrderPublicWithToken:
    # 1. Guest dine-in only — pickup/delivery is out of scope for v1.
    if payload.order_type != OrderType.DINE_IN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only dine_in orders are supported on the public endpoint",
        )

    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must contain at least one item",
        )

    restaurant = session.get(Restaurant, restaurant_id)
    if restaurant is None or restaurant.disabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found",
        )

    table = session.get(RestaurantTable, payload.restaurant_table_id)
    if table is None or table.restaurant_id != restaurant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found",
        )

    # Validate every menu_item_id in a single IN query.
    item_ids = [it.menu_item_id for it in payload.items]
    menu_items = session.exec(
        select(MenuItem).where(MenuItem.id.in_(item_ids))
    ).all()
    by_id = {mi.id: mi for mi in menu_items}
    for it in payload.items:
        mi = by_id.get(it.menu_item_id)
        if mi is None or mi.restaurant_id != restaurant_id or not mi.active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"menu_item {it.menu_item_id} is unavailable",
            )

    # Compute totals server-side from the current menu_item.price snapshot.
    total = 0.0
    order = Order(
        restaurant_id=restaurant_id,
        restaurant_table_id=table.id,
        order_type=OrderType.DINE_IN,
        order_status=OrderStatus.CREATED,
        payment_status=PaymentStatus.UNPAID,
        customer_id=None,
        contact_name=payload.contact_name,
        contact_phone=None,
        kitchen_note=payload.kitchen_note,
        tracking_token=_generate_tracking_token(),
    )
    session.add(order)
    session.flush()  # get order.id before inserting line items

    for it in payload.items:
        mi = by_id[it.menu_item_id]
        unit_price = float(mi.price)
        total += unit_price * it.quantity
        session.add(
            OrderMenuItem(
                order_id=order.id,
                menu_item_id=mi.id,
                quantity=it.quantity,
                notes=it.note,
                unit_price=unit_price,
            )
        )

    rounded_total = int(round(total))
    if rounded_total > _MAX_TOTAL_AMOUNT:
        # Catch buggy / malicious clients (BACKEND_PLAN §6).
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order total exceeds the configured maximum",
        )
    order.total_amount = rounded_total
    session.add(order)
    session.commit()
    session.refresh(order)

    public = _to_public(order)
    # Same event the kitchen UI already listens to — guest orders are
    # indistinguishable from authenticated ones from the staff side.
    background_tasks.add_task(
        manager.broadcast_to_restaurant,
        str(restaurant_id),
        {
            "type": "new_order",
            "source": "guest",
            "order_id": order.id,
            "order": public.model_dump_json(),
            "timestamp": datetime.now().isoformat(),
            "message": f"New guest order #{order.id}",
        },
    )

    return CustomerOrderPublicWithToken(
        order=public,
        tracking_token=order.tracking_token,
    )


# ── 4.3  GET /public/orders/{id}?token=... ───────────────────────────────────

@router.get(
    "/orders/{order_id}",
    response_model=CustomerOrderPublic,
    dependencies=[Depends(rate_limit("public_orders_read", per_ip=120))],
)
def get_guest_order(
    order_id: int,
    session: SessionDep,
    response: Response,
    token: Annotated[str, Query(min_length=1, max_length=128)],
) -> CustomerOrderPublic:
    order = _load_guest_order(session, order_id, token)
    response.headers["Cache-Control"] = "no-store"
    return _to_public(order)


# ── 4.4  PATCH /public/orders/{id}/cancel?token=... ──────────────────────────

@router.patch(
    "/orders/{order_id}/cancel",
    response_model=CustomerOrderPublic,
    dependencies=[Depends(rate_limit("public_orders_cancel", per_ip=10))],
)
def cancel_guest_order(
    order_id: int,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    manager: Annotated[ConnectionManager, Depends(get_connection_manager)],
    token: Annotated[str, Query(min_length=1, max_length=128)],
) -> CustomerOrderPublic:
    order = _load_guest_order(session, order_id, token)

    if order.order_status == OrderStatus.CANCELLED:
        return _to_public(order)
    if order.order_status not in _CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Order can no longer be cancelled "
                f"(current status: {order.order_status.value})."
            ),
        )

    order.order_status = OrderStatus.CANCELLED
    order.updated_at = datetime.now()
    session.add(order)
    session.commit()
    session.refresh(order)

    public = _to_public(order)
    if order.restaurant_id is not None:
        background_tasks.add_task(
            manager.broadcast_to_restaurant,
            str(order.restaurant_id),
            {
                "type": "order_cancelled",
                "source": "guest",
                "order_id": order.id,
                "order": public.model_dump_json(),
                "timestamp": datetime.now().isoformat(),
                "message": f"Guest cancelled order #{order.id}",
            },
        )
    return public
