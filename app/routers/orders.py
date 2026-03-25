from datetime import date, datetime
from typing import Annotated, List, Union
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlmodel import SQLModel, and_, func, select

from app.configs.database_configs import SessionDep
from app.cores.permissions import require_permission
from app.models.models import MenuItem, Order, OrderMenuItem, RestaurantTable, User
from app.schemas.auth_schemas import Role
from app.schemas.order_shemas import OrderCreate, OrderPublic, OrderStatus, OrderUpdate, PaymentStatus
from app.schemas.order_menu_item_schemas import OrderMenuItemStatusUpdate, OrderMenuItemPublic
from app.services.auth_service import get_current_active_user
from app.services.ws_service import ConnectionManager, get_connection_manager


router = APIRouter(tags=["orders"], dependencies=[Depends(get_current_active_user)])

@router.post("/orders", response_model=OrderPublic, dependencies=[require_permission("orders", "create")])
def create_order(order_data: OrderCreate, session: SessionDep, background_tasks: BackgroundTasks,
   current_user: Annotated[User, Depends(get_current_active_user)],  manager: ConnectionManager = Depends(get_connection_manager)): 
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
            server_id=current_user.id,
            total_amount=order_data.total_amount,
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

        order_query = session.get(Order, db_order.id)
    
    # Convert to OrderPublic (use model_dump, not model_dump_json)
        order_public = OrderPublic.model_validate(order_query)

        #notify all concerned restaurant
        background_tasks.add_task(
            manager.broadcast_to_restaurant,
            current_user.restaurant_id,
            {
                "type": "new_order",
                "order": order_public.model_dump_json(),
                "timestamp": datetime.now().isoformat(),
                "message": f"New order #{db_order.id} created"
            }
    )
        
        return db_order

@router.patch("/orders/{order_id}", response_model=OrderPublic, dependencies=[require_permission("orders", "update")])
def update_order(order_id: int, order: OrderUpdate,session: SessionDep, background_tasks: BackgroundTasks,
   current_user: Annotated[User, Depends(get_current_active_user)],  manager: ConnectionManager = Depends(get_connection_manager)):
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

    order_query = session.get(Order, order_db.id)
    
    # Convert to OrderPublic (use model_dump, not model_dump_json)
    order_public = OrderPublic.model_validate(order_query)

        #notify all concerned restaurant
    background_tasks.add_task(
            manager.broadcast_to_restaurant,
            current_user.restaurant_id,
            {
                "type": "order_updated",
                "order": order_public.model_dump_json(),
                "timestamp": datetime.now().isoformat(),
                "message": f"New order #{order_db.id} created"
            }
    )
        
    return order_db

class OrderStatusUpdate(SQLModel):
    status: OrderStatus

@router.patch("/orders/{order_id}/status", response_model=OrderPublic, dependencies=[require_permission("orders", "update")])
def change_order_status(order_id: int, session: SessionDep, order_status: OrderStatusUpdate, background_tasks: BackgroundTasks, current_user: Annotated[User, Depends(get_current_active_user)], manager: ConnectionManager = Depends(get_connection_manager)):
    order_db= session.get(Order, order_id)
    if not order_db:
        raise HTTPException(status_code=404, detail="Order not found")
    order_db.order_status= order_status.status
    session.add(order_db)
    session.commit()
    session.refresh(order_db)
    background_tasks.add_task(
            manager.broadcast_to_restaurant,
            current_user.restaurant_id,
            {
                "type": "update_order_status",
                "order_id": order_db.id,
                "new_status":order_status.status,
                "timestamp": datetime.now().isoformat(),
                "message": f"order #{order_db.id} updated"
            }
    )
    return order_db

@router.patch("/orders/items/{item_id}/status", response_model=OrderMenuItemPublic, dependencies=[require_permission("orders", "update")])
def change_order_menu_item_status(
    item_id: int, 
    status_update: OrderMenuItemStatusUpdate, 
    session: SessionDep, 
    background_tasks: BackgroundTasks, 
    current_user: Annotated[User, Depends(get_current_active_user)], 
    manager: ConnectionManager = Depends(get_connection_manager)
):
    item_db = session.get(OrderMenuItem, item_id)
    if not item_db:
        raise HTTPException(status_code=404, detail="Order menu item not found")
    
    item_db.status = status_update.status
    session.add(item_db)
    session.commit()
    session.refresh(item_db)
    
    # Notify restaurant
    background_tasks.add_task(
        manager.broadcast_to_restaurant,
        current_user.restaurant_id,
        {
            "type": "update_order_menu_item_status",
            "order_id": item_db.order_id,
            "item_id": item_db.id,
            "new_status": status_update.status,
            "timestamp": datetime.now().isoformat(),
            "message": f"Order menu item #{item_db.id} updated to {status_update.status}"
        }
    )
    
    return item_db

class OrderPaymentUpdate(SQLModel):
    status: PaymentStatus


@router.patch("/orders/{order_id}/payment", response_model=OrderPublic, dependencies=[require_permission("payments", "create")])
def change_order_status(order_id: int, session: SessionDep, payment_status: PaymentStatus):
    order_db= session.get(Order, order_id)
    if not order_db:
        raise HTTPException(status_code=404, detail="Order not found")
    order_db.payment_status= payment_status
    session.add(order_db)
    session.commit()
    session.refresh(order_db)
    return order_db

@router.get("/orders", response_model=List[OrderPublic], dependencies=[require_permission("orders", "read")])
def read_user_orders(
    today_only: Union[bool, None],
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = 0,
    limit: int = 100,
):
    # Build the base query based on user role
    from app.services.permission_service import _load_role_name
    role_name = _load_role_name(current_user, session)
    
    if role_name in ["admin", "super_admin", "cook", "cashier"]:
        # These roles should see all orders for the restaurant
        query = select(Order).join(RestaurantTable).where(RestaurantTable.restaurant_id == current_user.restaurant_id)
    else:
        # Others (like servers) see only their own orders
        query = select(Order).where(Order.server_id == current_user.id)
    
    # Add date filter if needed
    if today_only:
        query = query.where(func.date(Order.created_at) == date.today())
    
    # Add ordering for consistent pagination
    query = query.order_by(Order.created_at.desc())
    
    # Apply pagination
    query = query.offset(skip).limit(limit)
    
    # Execute query
    orders = session.exec(query).all()
    # Filter out orders with None menu_items
    valid_orders = []
    for order in orders:
        # Check if all menu_items are valid
        if all(item.menu_item is not None for item in order.order_menu_items):
            valid_orders.append(order)
    
    return valid_orders

@router.get("/orders/restaurant", response_model=List[OrderPublic], dependencies=[require_permission("orders", "read")])
def read_restaurant_orders(session: SessionDep, current_user: Annotated[User, Depends(get_current_active_user)]):
    orders = session.exec(select(Order).join(RestaurantTable).where(RestaurantTable.restaurant_id == current_user.restaurant_id)).all()
    return orders

@router.delete("/orders/{order_id}", dependencies=[require_permission("orders", "delete")])
def delete_order(order_id: int, session: SessionDep, background_tasks: BackgroundTasks, current_user: Annotated[User, Depends(get_current_active_user)], manager: ConnectionManager = Depends(get_connection_manager)):
    order= session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order item not found")
    session.delete(order)
    session.commit()
    background_tasks.add_task(
            manager.broadcast_to_restaurant,
            current_user.restaurant_id,
            {
                "type": "order_deleted",
                "order_id": order.id,
                "timestamp": datetime.now().isoformat(),
                "message": f"New order #{order.id} created"
            }
    )
    return order.id