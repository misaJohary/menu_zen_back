from datetime import datetime
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.configs.database_configs import SessionDep
from app.cores.permissions import require_permission
from app.models.models import Kitchen, KitchenUserLink, User
from app.schemas.kitchen_schemas import KitchenCreate, KitchenPublic, KitchenUpdate, KitchenWithUsers, UserInKitchen
from app.services.auth_service import get_current_active_user

router = APIRouter(
    tags=["kitchens"],
    dependencies=[Depends(get_current_active_user)],
)


def _get_kitchen_or_404(kitchen_id: int, restaurant_id: int, session: SessionDep) -> Kitchen:
    """Fetch a kitchen and verify it belongs to the current user's restaurant."""
    kitchen = session.get(Kitchen, kitchen_id)
    if not kitchen:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kitchen not found")
    if kitchen.restaurant_id != restaurant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return kitchen


# ── POST /kitchens ─────────────────────────────────────────────────────────────

@router.post(
    "/kitchens",
    response_model=KitchenPublic,
    dependencies=[require_permission("kitchens", "create")],
)
def create_kitchen(
    kitchen_in: KitchenCreate,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    kitchen = Kitchen(
        restaurant_id=current_user.restaurant_id,
        name=kitchen_in.name,
        active=kitchen_in.active,
    )
    session.add(kitchen)
    session.commit()
    session.refresh(kitchen)
    return kitchen


# ── GET /kitchens ──────────────────────────────────────────────────────────────

@router.get(
    "/kitchens",
    response_model=List[KitchenWithUsers],
    dependencies=[require_permission("kitchens", "read")],
)
def list_kitchens(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    kitchens = session.exec(
        select(Kitchen).where(Kitchen.restaurant_id == current_user.restaurant_id)
    ).all()

    result = []
    for kitchen in kitchens:
        links = session.exec(
            select(KitchenUserLink).where(KitchenUserLink.kitchen_id == kitchen.id)
        ).all()
        users = [
            UserInKitchen.model_validate(session.get(User, link.user_id))
            for link in links
            if session.get(User, link.user_id)
        ]
        result.append(KitchenWithUsers(**kitchen.model_dump(), users=users))

    return result


# ── GET /kitchens/{kitchen_id} ─────────────────────────────────────────────────

@router.get(
    "/kitchens/{kitchen_id}",
    response_model=KitchenPublic,
    dependencies=[require_permission("kitchens", "read")],
)
def get_kitchen(
    kitchen_id: int,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return _get_kitchen_or_404(kitchen_id, current_user.restaurant_id, session)


# ── PATCH /kitchens/{kitchen_id} ───────────────────────────────────────────────

@router.patch(
    "/kitchens/{kitchen_id}",
    response_model=KitchenPublic,
    dependencies=[require_permission("kitchens", "update")],
)
def update_kitchen(
    kitchen_id: int,
    kitchen_in: KitchenUpdate,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    kitchen = _get_kitchen_or_404(kitchen_id, current_user.restaurant_id, session)

    if kitchen_in.name is not None:
        kitchen.name = kitchen_in.name
    if kitchen_in.active is not None:
        kitchen.active = kitchen_in.active

    kitchen.updated_at = datetime.now()
    session.add(kitchen)
    session.commit()
    session.refresh(kitchen)
    return kitchen


# ── DELETE /kitchens/{kitchen_id} ──────────────────────────────────────────────

@router.delete(
    "/kitchens/{kitchen_id}",
    dependencies=[require_permission("kitchens", "delete")],
)
def delete_kitchen(
    kitchen_id: int,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    kitchen = _get_kitchen_or_404(kitchen_id, current_user.restaurant_id, session)
    session.delete(kitchen)
    session.commit()
    return {"ok": True}


# ── POST /kitchens/{kitchen_id}/users/{user_id} ────────────────────────────────

@router.post(
    "/kitchens/{kitchen_id}/users/{user_id}",
    dependencies=[require_permission("kitchens", "update")],
)
def assign_cook_to_kitchen(
    kitchen_id: int,
    user_id: int,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    kitchen = _get_kitchen_or_404(kitchen_id, current_user.restaurant_id, session)

    target_user = session.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target_user.restaurant_id != current_user.restaurant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not in your restaurant")
    if not target_user.role or target_user.role.name != "cook":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not a cook")

    existing = session.exec(
        select(KitchenUserLink).where(
            KitchenUserLink.kitchen_id == kitchen.id,
            KitchenUserLink.user_id == user_id,
        )
    ).first()
    if not existing:
        session.add(KitchenUserLink(kitchen_id=kitchen.id, user_id=user_id))
        session.commit()

    return {"ok": True}


# ── DELETE /kitchens/{kitchen_id}/users/{user_id} ─────────────────────────────

@router.delete(
    "/kitchens/{kitchen_id}/users/{user_id}",
    dependencies=[require_permission("kitchens", "update")],
)
def remove_cook_from_kitchen(
    kitchen_id: int,
    user_id: int,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    kitchen = _get_kitchen_or_404(kitchen_id, current_user.restaurant_id, session)

    link = session.exec(
        select(KitchenUserLink).where(
            KitchenUserLink.kitchen_id == kitchen.id,
            KitchenUserLink.user_id == user_id,
        )
    ).first()
    if link:
        session.delete(link)
        session.commit()

    return {"ok": True}
