from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.models.models import MenuItem, Order
from app.schemas.order_shemas import OrderCreate, OrderPublic


router = APIRouter(tags=["orders"])

@router.post("/orders", response_model= OrderPublic)
def create_order(order: OrderCreate, session: SessionDep):
    menu_items = session.exec(
        select(MenuItem).where(MenuItem.id.in_(order.menu_items_id))
    ).all()

    if len(menu_items) != len(order.menu_items_id):
        raise HTTPException(status_code=404, detail="Certains menu items n'existent pas")

    order_dict = Order.model_dump(order, exclude={"menu_items_id"})
    db_order = Order(**order_dict)
    
    # Assigner les menu items
    db_order.menu_items = menu_items
    
    session.add(db_order)
    session.commit()
    session.refresh(db_order)
 
    return db_order