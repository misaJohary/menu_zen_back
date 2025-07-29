from fastapi import FastAPI
import uvicorn

from app.routers import categories, menu_items

from .configs.database_configs import create_db_and_tables

from .routers import auth

app = FastAPI()

if __name__ == "__main__":
    uvicorn.run(app, host=8000)

@app.on_event("startup")
def on_startup():
    create_db_and_tables()


app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(menu_items.router)


@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}