from fastapi import Depends, FastAPI

from .dependencies import get_query_token, get_token_header
from .routers import auth, orders, menu

app = FastAPI()


app.include_router(auth.router)


@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}