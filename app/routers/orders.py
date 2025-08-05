from typing import Annotated, List
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import SQLModel, select

from app.configs.database_configs import SessionDep
from app.models.models import MenuItem, Order, User
from app.schemas.auth_schemas import Role
from app.schemas.order_shemas import OrderCreate, OrderPublic, OrderStatus, PaymentStatus
from app.services.auth_service import get_current_active_user


router = APIRouter(tags=["orders"], dependencies=[Depends(get_current_active_user)])

@router.post("/orders", response_model= OrderPublic)
def create_order(order: OrderCreate, session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):

    menu_items_id = list()
    [menu_items_id.append(menu.menu_item_id) for menu in order.menu_items]
        

    menu_items = session.exec(
        select(MenuItem).where(MenuItem.id.in_(menu_items_id))
    ).all()

    order_dict = Order.model_dump(order, exclude={"menu_items"})
    db_order = Order(**order_dict)
    
    # Assign menu items
    db_order.menu_items = menu_items
    db_order.server_id= current_user.id
    
    session.add(db_order)
    session.commit()
    session.refresh(db_order)
 
    return db_order

class OrderStatusUpdate(SQLModel):
    status: OrderStatus

@router.patch("/orders/{order_id}/status")
def change_order_status(order_id: int, session: SessionDep, order_status: OrderStatusUpdate):
    order_db= session.get(Order, order_id)
    if not order_db:
        raise HTTPException(status_code=404, detail="Order not found")
    order_db.order_status= order_status.status
    session.add(order_db)
    session.commit()
    session.refresh(order_db)
    return order_db

class OrderPaymentUpdate(SQLModel):
    status: PaymentStatus


@router.patch("/orders/{order_id}/payment")
def change_order_status(order_id: int, session: SessionDep, payment_status: PaymentStatus):
    order_db= session.get(Order, order_id)
    if not order_db:
        raise HTTPException(status_code=404, detail="Order not found")
    order_db.payment_status= payment_status.status
    session.add(order_db)
    session.commit()
    session.refresh(order_db)
    return order_db

@router.get("/orders", response_model=List[OrderPublic])
def read_user_orders(session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    if current_user.roles is Role.ADMIN:
        return session.exec(select(Order).where(Order.server.restaurant_id == current_user.restaurant_id)).all()
    orders = session.exec(select(Order).where(Order.server_id == current_user.id)).all()
    return orders