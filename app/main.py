from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

from app.routers import categories, menu, menu_items, restaurant

from .configs.database_configs import create_db_and_tables

from .routers import auth

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup events
    print("Application starting up...")
    create_db_and_tables()
    yield
    # Shutdown events
    print("Application shutting down...")

app = FastAPI(lifespan=lifespan)

if __name__ == "__main__":
    uvicorn.run(app, host=8000)


app.include_router(auth.router)
app.include_router(restaurant.router)
app.include_router(menu.router)
app.include_router(categories.router)
app.include_router(menu_items.router)


@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}