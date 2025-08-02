from fastapi import APIRouter

from app.configs.database_configs import SessionDep
from app.models.models import RestaurantTable
from app.schemas.restaurant_table_schemas import RestaurantTableCreate


router = APIRouter(tags= ["tables"])

@router.post("/tables")
def create_table(table: RestaurantTableCreate, session: SessionDep):
    db_table = RestaurantTable.model_validate(table)
    session.add(db_table)
    session.commit()
    session.refresh(db_table)
    return db_table