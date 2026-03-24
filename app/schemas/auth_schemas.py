from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel
from sqlmodel import Field, SQLModel

from app.schemas.restaurant_schemas import RestaurantPublic


# ── Token schemas ─────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Union[str, None] = None


# ── Role name enum ────────────────────────────────────────────────────────────
# Renamed from `Role` to `RoleName` to avoid collision with the ORM Role model.
# A module-level alias keeps any old import of `Role` working in existing routers.

class RoleName(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    SERVER = "server"
    CASHIER = "cashier"
    COOK = "cook"  # ← newly added


# Backward-compatible alias so existing code that does
# `from app.schemas.auth_schemas import Role` still works.
Role = RoleName


# ── User schemas ──────────────────────────────────────────────────────────────

class UserBase(SQLModel):
    username: str
    email: Union[str, None] = None
    full_name: Union[str, None] = None
    disabled: bool = True

    restaurant_id: Union[int, None] = Field(default=None, foreign_key="restaurant.id")

    # RBAC: FK to the roles table (replaces the old plain `roles` enum string column)
    role_id: Union[int, None] = Field(default=None, foreign_key="roles.id")


class UserCreate(UserBase):
    password: str
    # Optional convenience field — if omitted, we'll try to use role_id from the base
    role_name: Optional[RoleName] = None


class UserUpdate(SQLModel):
    username: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    # Accept either the integer FK or the friendly name; router resolves name → id
    role_id: Optional[int] = None
    role_name: Optional[RoleName] = None


from pydantic import BaseModel, model_validator

class UserPublic(SQLModel):
    id: int
    username: str
    email: Union[str, None] = None
    full_name: Union[str, None] = None
    disabled: bool
    restaurant_id: Union[int, None] = None
    role_id: Union[int, None] = None
    # This field is filled dynamically by the validator below
    role_name: Optional[str] = None
    must_change_password: bool = False

    @model_validator(mode="before")
    @classmethod
    def populate_role_name(cls, data: Any) -> Any:
        # If we are working with an ORM model (has a 'role' relationship)
        # we pull the name from it before Pydantic converts to model.
        if hasattr(data, "role"):
            role_obj = getattr(data, "role", None)
            if role_obj and hasattr(role_obj, "name"):
                # Convert the object to a dict if it isn't one yet
                # so we can inject the extra 'role_name' field.
                if hasattr(data, "model_dump"):
                    result = data.model_dump()
                elif hasattr(data, "__dict__"):
                    result = dict(data.__dict__)
                else:
                    return data
                
                result["role_name"] = role_obj.name
                return result
        return data


class UserRestaurant(SQLModel):
    user: UserPublic
    restaurant: Optional[RestaurantPublic] = None
    token: Optional[Token] = None