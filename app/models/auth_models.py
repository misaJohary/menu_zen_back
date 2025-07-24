from ..routers.auth import User


class UserInDB(User):
    hashed_password: str