from typing import Annotated, List
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import SQLModel, select

from app.configs.database_configs import SessionDep
from app.models.models import MenuItem, Order, OrderMenuItem, RestaurantTable, User
from app.schemas.auth_schemas import Role
from app.schemas.order_shemas import OrderCreate, OrderPublic, OrderStatus, OrderUpdate, PaymentStatus
from app.services.auth_service import get_current_active_user


router = APIRouter(tags=["orders"], dependencies=[Depends(get_current_active_user)])

@router.post("/orders", response_model= OrderPublic)
def create_order(order_data: OrderCreate, session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]): 
        # Validate restaurant table exists
        table_query = select(RestaurantTable).where(RestaurantTable.id == order_data.restaurant_table_id) 
        restaurant_table = session.exec(table_query).first()
        if not restaurant_table:
            raise HTTPException(
                status_code=404,
                detail="Restaurant table not found"
            )
        # Validate server exists if provided
        if order_data.server_id:
            server_query = select(User).where(User.id == order_data.server_id)
            server = session.exec(server_query).first()
            if not server:
                raise HTTPException(
                    status_code=404,
                    detail="Server not found"
                )
        # Create the order (without menu items first)
        db_order = Order(
            restaurant_table_id=order_data.restaurant_table_id,
            order_status=order_data.order_status,
            payment_status=order_data.payment_status,
            client_name=order_data.client_name,
            server_id=current_user.id
        )
        session.add(db_order)
        session.commit()
        session.refresh(db_order)
        # Add menu items to the order
        for item_data in order_data.order_menu_items:
            # Get menu item to validate and get current price
            menu_item = session.get(MenuItem, item_data.menu_item_id)
            
            if not menu_item:
                # Rollback the order if menu item doesn't exist
                session.delete(db_order)
                session.commit()
                raise HTTPException(
                    status_code=404,
                    detail=f"Menu item with id {item_data.menu_item_id} not found"
                )
            
            # Create order menu item
            db_order_item = OrderMenuItem(
                order_id=db_order.id,
                menu_item_id=item_data.menu_item_id,
                quantity=item_data.quantity,
                notes=item_data.notes,
                unit_price=item_data.unit_price 
            )
            
            session.add(db_order_item)
        
        session.commit()
        session.refresh(db_order)
        
        return db_order

@router.patch("/orders/{order_id}", response_model= OrderPublic)
def update_order(order_id: int, order: OrderUpdate, session: SessionDep):
    order_db= session.get(Order, order_id)
    if not order_db:
        raise HTTPException(status_code=404, detail="Order not found")
    order_data = order.model_dump(exclude_unset= True, exclude={'order_menu_items'})
    order_db.sqlmodel_update(order_data)
    session.add(order_db)
    session.commit()
    session.refresh(order_db)
    for order_item in order_db.order_menu_items:
        session.delete(order_item)

    for item_data in order.order_menu_items:
            db_order_item = OrderMenuItem(
                order_id=order_id,
                menu_item_id=item_data.menu_item_id,
                quantity=item_data.quantity,
                notes=item_data.notes,
                unit_price=item_data.unit_price 
            )
            session.add(db_order_item)
    
    session.commit()
    session.refresh(order_db)
        
    return order_db

class OrderStatusUpdate(SQLModel):
    status: OrderStatus

@router.patch("/orders/{order_id}/status", response_model= OrderPublic)
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


@router.patch("/orders/{order_id}/payment", response_model= OrderPublic)
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
    #if current_user.roles is Role.ADMIN:
        #return session.exec(select(Order).where(Order.server.restaurant_id == current_user.restaurant_id)).all()
    orders = session.exec(select(Order).where(Order.server_id == current_user.id)).all()
    return orders

@router.delete("/orders/{order_id}")
def delete_order(order_id: int, session: SessionDep):
    order= session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order item not found")
    session.delete(order)
    session.commit()
    return {
        "message": "successfully deleted"
    }