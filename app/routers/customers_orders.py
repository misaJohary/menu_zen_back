from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.enums.order_type import OrderType
from app.models.models import (
    Customer,
    MenuItem,
    Order,
    OrderMenuItem,
    Restaurant,
    RestaurantTable,
)
from app.schemas.order_shemas import (
    CustomerOrderCreate,
    CustomerOrderItemPublic,
    CustomerOrderPublic,
    OrderStatus,
    PaymentStatus,
)
from app.services.customer_auth_service import get_current_customer
from app.services.ws_service import ConnectionManager, get_connection_manager


router = APIRouter(prefix="/customers/me/orders", tags=["customers"])


# Customer can cancel only while the order is still pending — staff have
# not yet started cooking.
_CANCELLABLE_STATUSES = {OrderStatus.CREATED}


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
        order_type=order.order_type,
        order_status=order.order_status,
        payment_status=order.payment_status,
        contact_name=order.contact_name,
        contact_phone=order.contact_phone,
        scheduled_for=order.scheduled_for,
        total_amount=float(order.total_amount) if order.total_amount is not None else None,
        items=items,
        created_at=order.created_at,
    )


@router.post("", response_model=CustomerOrderPublic, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: CustomerOrderCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    current: Annotated[Customer, Depends(get_current_customer)],
    manager: Annotated[ConnectionManager, Depends(get_connection_manager)],
) -> CustomerOrderPublic:
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Order must contain at least one item",
        )

    restaurant = session.get(Restaurant, payload.restaurant_id)
    if restaurant is None or restaurant.disabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found",
        )

    # Dine-in must include a table belonging to the same restaurant.
    if payload.order_type == OrderType.DINE_IN:
        if payload.restaurant_table_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="restaurant_table_id is required for dine_in orders",
            )
        table = session.get(RestaurantTable, payload.restaurant_table_id)
        if table is None or table.restaurant_id != payload.restaurant_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Table does not belong to this restaurant",
            )

    # Validate every menu_item_id in a single IN query.
    item_ids = [it.menu_item_id for it in payload.items]
    menu_items = session.exec(
        select(MenuItem).where(MenuItem.id.in_(item_ids))
    ).all()
    by_id = {mi.id: mi for mi in menu_items}
    for it in payload.items:
        mi = by_id.get(it.menu_item_id)
        if mi is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"menu_item {it.menu_item_id} not found",
            )
        if not mi.active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"menu_item {it.menu_item_id} is not available",
            )
        if mi.restaurant_id != payload.restaurant_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"menu_item {it.menu_item_id} does not belong to this restaurant",
            )

    # Compute totals server-side from the current menu_item.price.
    total = 0.0
    order = Order(
        restaurant_id=payload.restaurant_id,
        restaurant_table_id=(
            payload.restaurant_table_id
            if payload.order_type == OrderType.DINE_IN
            else None
        ),
        order_type=payload.order_type,
        order_status=OrderStatus.CREATED,
        payment_status=PaymentStatus.UNPAID,
        customer_id=current.id,
        contact_name=payload.contact_name or current.full_name,
        contact_phone=payload.contact_phone or current.phone,
        scheduled_for=payload.scheduled_for,
    )
    session.add(order)
    session.flush()  # get order.id

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

    order.total_amount = int(round(total))
    session.add(order)
    session.commit()
    session.refresh(order)

    public = _to_public(order)
    background_tasks.add_task(
        manager.broadcast_to_restaurant,
        str(payload.restaurant_id),
        {
            "type": "new_order",
            "source": "customer",
            "order_id": order.id,
            "order": public.model_dump_json(),
            "timestamp": datetime.now().isoformat(),
            "message": f"New customer order #{order.id}",
        },
    )
    return public


@router.get("", response_model=list[CustomerOrderPublic])
def list_my_orders(
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
    status_filter: Annotated[Optional[OrderStatus], Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CustomerOrderPublic]:
    statement = (
        select(Order)
        .where(Order.customer_id == current.id)
        .order_by(Order.created_at.desc())
    )
    if status_filter is not None:
        statement = statement.where(Order.order_status == status_filter)
    statement = statement.offset(offset).limit(limit)
    rows = session.exec(statement).all()
    return [_to_public(o) for o in rows]


@router.get("/{order_id}", response_model=CustomerOrderPublic)
def get_my_order(
    order_id: int,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> CustomerOrderPublic:
    order = session.get(Order, order_id)
    if order is None or order.customer_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return _to_public(order)


@router.patch("/{order_id}/cancel", response_model=CustomerOrderPublic)
def cancel_my_order(
    order_id: int,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    current: Annotated[Customer, Depends(get_current_customer)],
    manager: Annotated[ConnectionManager, Depends(get_connection_manager)],
) -> CustomerOrderPublic:
    order = session.get(Order, order_id)
    if order is None or order.customer_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    if order.order_status == OrderStatus.CANCELLED:
        return _to_public(order)
    if order.order_status not in _CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Order can no longer be cancelled by the customer "
                f"(current status: {order.order_status.value}). "
                "Please contact the restaurant."
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
                "source": "customer",
                "order_id": order.id,
                "order": public.model_dump_json(),
                "timestamp": datetime.now().isoformat(),
                "message": f"Customer cancelled order #{order.id}",
            },
        )
    return public
