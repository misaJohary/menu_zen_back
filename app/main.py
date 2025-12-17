from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.routers import categories, languages, menu, menu_items, orders, restaurant, restaurant_table, stats, ws_connect

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

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

if __name__ == "__main__":
    uvicorn.run(app, host=8000)


app.include_router(auth.router)
app.include_router(restaurant.router)
app.include_router(menu.router)
app.include_router(categories.router)
app.include_router(menu_items.router)
app.include_router(orders.router)
app.include_router(restaurant_table.router)
app.include_router(languages.router)
app.include_router(ws_connect.router)
app.include_router(stats.router)


@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}