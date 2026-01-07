from datetime import date, timedelta
from statistics import mean
from typing import Annotated, List, Literal, Optional, Union
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Enum, and_, func, select

from app.configs.database_configs import SessionDep
from app.models.models import MenuItem, Order, OrderMenuItem, RestaurantTable, User
from app.schemas.order_shemas import OrderStatus
from app.services.auth_service import get_current_active_user


router = APIRouter(
    tags=["stats"],
    dependencies= [Depends(get_current_active_user)])


class DailyOrderCount(BaseModel):
    date: date
    count: int

class OrderCount(BaseModel):
    value: int
    mean_count: float
    today_count: int

class OrderCountListResponse(BaseModel):
    daily_counts: List[DailyOrderCount]
    total_count: int
    mean_count: float
    today_count: int

@router.get("/stats/order-count", response_model=Union[OrderCountListResponse, OrderCount])
def get_order_count(
    session: SessionDep, 
    current_user: Annotated[User, Depends(get_current_active_user)],
    period: Optional[
        Literal[
            "today",
            "yesterday",
            "last_7_days",
            "last_30_days",
            "this_week",
            "this_month"
        ]
    ] = None,
    days: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    restaurant_id = current_user.restaurant_id
    
    # Get date range
    if days is None and period is None and start_date is None:
        # Default to today only
        date_start = date.today()
        date_end = date.today()
        return_daily_list = False
    else:
        date_start, date_end = get_date_range(period, days, start_date, end_date)
        return_daily_list = days is not None
    
    orders = session.exec(
        select(Order).where(
            and_(
                func.date(Order.created_at) >= date_start,
                func.date(Order.created_at) <= date_end,
                Order.r_table.has(restaurant_id=restaurant_id),
            )
        )
    ).all()
    
    total_count = len(orders)
    
    # Get today's count
    today = date.today()
    today_orders = session.exec(
        select(Order).where(
            and_(
                func.date(Order.created_at) == today,
                Order.r_table.has(restaurant_id=restaurant_id),
            )
        )
    ).all()
    today_count = len(today_orders)
    
    if return_daily_list:
        # Group orders by date and count
        from collections import defaultdict
        daily_data = defaultdict(int)
        
        for order in orders:
            order_date = order.created_at.date()
            daily_data[order_date] += 1
        
        # Create list of daily counts
        daily_counts = [
            DailyOrderCount(date=order_date, count=count)
            for order_date, count in sorted(daily_data.items())
        ]
        
        # Calculate mean daily count
        mean_count = total_count / len(daily_counts) if daily_counts else 0.0
        
        return OrderCountListResponse(
            daily_counts=daily_counts,
            total_count=total_count,
            mean_count=mean_count,
            today_count=today_count
        )
    else:
        # Calculate number of days in the period
        days_in_period = (date_end - date_start).days + 1
        
        # Calculate mean daily count
        mean_count = total_count / days_in_period if days_in_period > 0 else 0.0
        
        # Return simple count with mean
        return OrderCount(
            value=total_count,
            mean_count=mean_count,
            today_count=today_count
        )



def get_date_range(period: Optional[str] = None, days: Optional[int] = None,
                   start_date: Optional[date] = None, end_date: Optional[date] = None):

    today = date.today()

    # Explicit start/end override
    if start_date and end_date:
        return start_date, end_date

    # Last X days
    if days:
        return today - timedelta(days=days), today

    if period:
        if period == "today":
            return today, today
        elif period == "yesterday":
            y = today - timedelta(days=1)
            return y, y
        elif period == "last_7_days":
            return today - timedelta(days=7), today
        elif period == "last_30_days":
            return today - timedelta(days=30), today
        elif period == "this_week":
            start = today - timedelta(days=today.weekday())
            return start, today
        elif period == "this_month":
            start = today.replace(day=1)
            return start, today

    return today, today

class DailyRevenue(BaseModel):
    date: date
    revenue: float

class RevenueSummary(BaseModel):
    revenue: float

class RevenueListResponse(BaseModel):
    today_revenue: float
    daily_revenues: List[DailyRevenue]
    total_revenue: float
    mean_revenue: float
    diff_percentage: float

@router.get("/stats/revenue", response_model=Union[RevenueListResponse, RevenueSummary])
def get_revenue(
    session: SessionDep, 
    current_user: Annotated[User, Depends(get_current_active_user)],
    period: Optional[
        Literal[
            "today",
            "yesterday",
            "last_7_days",
            "last_30_days",
            "this_week",
            "this_month"
        ]
    ] = None,
    days: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    date_start, date_end = get_date_range(period, days, start_date, end_date)
    
    # Check if we need to return daily breakdown
    return_daily_list = days is not None
    
    orders = session.exec(
        select(Order).where(
            and_(
                func.date(Order.created_at) >= date_start,
                func.date(Order.created_at) <= date_end,
                Order.server_id == current_user.id
                #Order.order_status.in_(['completed', 'paid'])
            )
        )
    ).all()
    
    if return_daily_list:
        # Group orders by date and calculate daily revenue
        from collections import defaultdict
        daily_data = defaultdict(float)
        
        for order in orders:
            order_date = order.created_at.date()
            daily_data[order_date] += order.total_amount
        
        # Create list of daily revenues
        daily_revenues = [
            DailyRevenue(date=order_date, revenue=revenue)
            for order_date, revenue in sorted(daily_data.items())
        ]
        
        total_revenue = sum(order.total_amount for order in orders)
        
        today = date.today()
        completed_days = [
            d.revenue for d in daily_revenues
            if d.date < today
        ]

        mean_revenue = mean(completed_days) if completed_days else 0

        today_rev = daily_data.get(date.today(), 0.0)
        mean_rev = mean_revenue  # already computed earlier

        if mean_rev > 0:
            diff_percentage = ((today_rev - mean_rev) / mean_rev) * 100
        else:
            # avoid division by zero
            diff_percentage = 0.0
        
        return RevenueListResponse(
            today_revenue=today_rev,
            daily_revenues=daily_revenues,
            total_revenue=total_revenue,
            mean_revenue= mean_revenue,
            diff_percentage= diff_percentage
        )
    else:
        # Return simple summary
        revenue = sum(order.total_amount for order in orders)
        return RevenueSummary(revenue=revenue)

class TopMenuItem(BaseModel):
    id: int
    name: str
    picture: str
    category: Optional[str] = None
    times_ordered: int
    total_quantity: int
    total_revenue: float
    #total_item_ordered: int
    #percentage_of_orders: float

@router.get("/stats/top-menu-items", response_model=List[TopMenuItem])
def get_top_menu_items(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int = 5,
    period: Optional[
        Literal[
            "today",
            "yesterday",
            "last_7_days",
            "last_30_days",
            "this_week",
            "this_month"
        ]
    ] = None,
    days: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    language: str = "en"
):
    restaurant_id = current_user.restaurant_id
    
    # Get date range
    date_start, date_end = get_date_range(period, days, start_date, end_date)
    
    # Get orders in date range
    statement = select(Order).where(
        and_(
            func.date(Order.created_at) >= date_start,
            func.date(Order.created_at) <= date_end,
            Order.r_table.has(restaurant_id=restaurant_id),
            Order.order_status != OrderStatus.CANCELLED
        )
    )
    orders = session.exec(statement).all()
    
    # Aggregate menu item statistics
    item_stats = {}
    
    for order in orders:
        if not order.order_menu_items:
            continue
            
        for order_item in order.order_menu_items:
            # Skip if menu item doesn't exist anymore
            menu_item = order_item.menu_item
            if not menu_item:
                continue
                
            menu_item_id = order_item.menu_item_id
            
            if menu_item_id not in item_stats:
                # Get name in specific language
                menu_item_name = "Unknown Item"
                if menu_item.translations:
                    translation = next(
                        (t for t in menu_item.translations if t.language_code == language),
                        None
                    )
                    if translation and translation.name:
                        menu_item_name = translation.name
                    elif len(menu_item.translations) > 0 and menu_item.translations[0].name:
                        menu_item_name = menu_item.translations[0].name
                
                # Get category name - safely handle missing category
                category_name = None
                if menu_item.category and menu_item.category.translations:
                    translation = next(
                        (t for t in menu_item.category.translations if t.language_code == language),
                        None
                    )
                    if translation and translation.name:
                        category_name = translation.name
                    elif len(menu_item.category.translations) > 0 and menu_item.category.translations[0].name:
                        category_name = menu_item.category.translations[0].name
                    
                item_stats[menu_item_id] = {
                    'id': menu_item_id,
                    'name': menu_item_name,
                    'picture': menu_item.picture if hasattr(menu_item, 'picture') else None,
                    'category': category_name,
                    'quantity': 0,
                    'times_ordered': 0,
                    'revenue': 0.0
                }
            
            # Update statistics
            item_stats[menu_item_id]['quantity'] += order_item.quantity
            item_stats[menu_item_id]['times_ordered'] += 1
            if order_item.unit_price:
                item_stats[menu_item_id]['revenue'] += (order_item.quantity * order_item.unit_price)
    
    # Sort by quantity and get top items
    sorted_items = sorted(
        item_stats.values(),
        key=lambda x: x['quantity'],
        reverse=True
    )[:limit]
    
    return [
        TopMenuItem(
            id=item['id'],
            name=item['name'],
            picture=item['picture'],
            category=item['category'],
            times_ordered=item['times_ordered'],
            total_quantity=item['quantity'],
            total_revenue=item['revenue'],
        )
        for item in sorted_items
    ]