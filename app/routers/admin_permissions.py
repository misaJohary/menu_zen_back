"""
Admin endpoints for per-user permission overrides.

GET  /admin/users/{user_id}/permissions
     Returns every system permission with its current status for that user.

PATCH /admin/users/{user_id}/permissions
     Apply or remove a permission override.
     Body: { "permission_id": int, "type": "grant" | "revoke" | "reset" }
"""

from enum import Enum
from typing import Annotated, List, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select, Session

from app.configs.database_configs import SessionDep
from app.cores.permissions import require_permission
from app.models.models import Permission, Role, User, UserPermission, UserPermissionType
from app.services import permission_service
from app.services.auth_service import get_current_active_user

router = APIRouter(
    prefix="/admin",
    tags=["admin-permissions"],
    dependencies=[Depends(get_current_active_user)],
)

# ── Pydantic v2 schemas ───────────────────────────────────────────────────────

class OverrideAction(str, Enum):
    GRANT = "grant"
    REVOKE = "revoke"
    RESET = "reset"  # Remove override → revert to role default


class PermissionOverrideRequest(BaseModel):
    permission_id: int
    type: OverrideAction


class PermissionStatusItem(BaseModel):
    permission_id: int
    resource: str
    action: str
    status: Literal["from_role", "granted", "revoked", "none"]


# ── Metadata schemas ──────────────────────────────────────────────────────────

class RolePublic(BaseModel):
    id: int
    name: str
    level: int


class PermissionPublic(BaseModel):
    id: int
    resource: str
    action: str
    description: str | None = None


# ── Internal helpers ──────────────────────────────────────────────────────────

PROTECTED_ROLE_NAMES = {"admin", "super_admin"}
SUPER_ADMIN_ROLE_NAME = "super_admin"


def _get_role_name(user: User, db: Session) -> str | None:
    """Return the role name for a user, or None if they have no role."""
    if user.role_id is None:
        return None
    role = db.get(Role, user.role_id)
    return role.name if role else None


def _assert_caller_is_admin_or_above(caller: User, db: Session) -> str:
    """Raise 403 if the caller is not at least an admin.
    Returns the caller's role name for further checks.
    """
    caller_role_name = _get_role_name(caller, db)
    if caller_role_name not in {"admin", "super_admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and super-admins can manage user permissions.",
        )
    return caller_role_name


def _assert_target_is_not_protected(
    target: User,
    caller_role_name: str,
    db: Session,
) -> None:
    """Raise 403 if the target user's role is protected and the caller isn't super_admin."""
    if caller_role_name == SUPER_ADMIN_ROLE_NAME:
        return  # super_admin can touch anyone
    target_role_name = _get_role_name(target, db)
    if target_role_name in PROTECTED_ROLE_NAMES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Cannot modify permissions for a user with role '{target_role_name}'. "
                "Only super_admin can do that."
            ),
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get(
    "/users/{user_id}/permissions",
    response_model=List[PermissionStatusItem],
    dependencies=[require_permission("users", "read")],
    summary="List all permissions with their current status for a user",
)
def get_user_permissions(
    user_id: int,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    # Caller must be admin or above
    caller_role_name = _assert_caller_is_admin_or_above(current_user, session)

    # Load target user
    target_user = session.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Non-super_admin cannot inspect admin/super_admin users
    _assert_target_is_not_protected(target_user, caller_role_name, session)

    # Delegate to service (returns list[dict])
    details = permission_service.get_user_permission_details(target_user, session)

    return [
        PermissionStatusItem(
            permission_id=d["permission_id"],
            resource=d["resource"],
            action=d["action"],
            status=d["status"],
        )
        for d in details
    ]


@router.patch(
    "/users/{user_id}/permissions",
    status_code=status.HTTP_200_OK,
    dependencies=[require_permission("users", "update")],
    summary="Grant, revoke, or reset a permission override for a user",
)
def patch_user_permission(
    user_id: int,
    body: PermissionOverrideRequest,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    # ── 1. Caller must be admin or above ──────────────────────────────────────
    caller_role_name = _assert_caller_is_admin_or_above(current_user, session)

    # ── 2. Load & validate target user ────────────────────────────────────────
    target_user = session.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot modify your own permissions.",
        )

    # ── 3. Target must not be a protected role (unless caller is super_admin) ─
    _assert_target_is_not_protected(target_user, caller_role_name, session)

    # ── 4. Load the permission being referenced ───────────────────────────────
    permission = session.get(Permission, body.permission_id)
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission with id={body.permission_id} not found",
        )

    # ── 5. Grant check: admin cannot grant what they don't hold ───────────────
    if body.type == OverrideAction.GRANT and caller_role_name != SUPER_ADMIN_ROLE_NAME:
        caller_can = permission_service.can(
            current_user, permission.resource, permission.action, session
        )
        if not caller_can:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"You cannot grant '{permission.resource}:{permission.action}' "
                    "because you don't hold that permission yourself."
                ),
            )

    # ── 6. Look up existing override (if any) ─────────────────────────────────
    existing_stmt = select(UserPermission).where(
        UserPermission.user_id == user_id,
        UserPermission.permission_id == body.permission_id,
    )
    existing = session.exec(existing_stmt).first()

    # ── 7. Apply the action ───────────────────────────────────────────────────
    if body.type == OverrideAction.RESET:
        # Delete override → user falls back to role-default behaviour
        if existing:
            session.delete(existing)
            session.commit()
        # Nothing to delete — silently succeed (idempotent)
        permission_service.invalidate_cache(user_id)
        return {"detail": "Permission override reset to role default."}

    # grant or revoke → upsert
    override_type = (
        UserPermissionType.GRANT
        if body.type == OverrideAction.GRANT
        else UserPermissionType.REVOKE
    )

    if existing:
        existing.type = override_type
        existing.granted_by = current_user.id
        session.add(existing)
    else:
        new_override = UserPermission(
            user_id=user_id,
            permission_id=body.permission_id,
            type=override_type,
            granted_by=current_user.id,
        )
        session.add(new_override)

    session.commit()

    # ── 8. Invalidate the resolved-permission cache for the target user ───────
    permission_service.invalidate_cache(user_id)

    action_label = "granted" if body.type == OverrideAction.GRANT else "revoked"
    return {
        "detail": (
            f"Permission '{permission.resource}:{permission.action}' "
            f"{action_label} for user {user_id}."
        )
    }


# ── Metadata Routes ───────────────────────────────────────────────────────────

@router.get(
    "/roles",
    response_model=List[RolePublic],
    dependencies=[require_permission("users", "read")],
    summary="List all available system roles",
)
def get_all_roles(session: SessionDep):
    """Retrieve all roles for use in user creation or assignment dropdowns."""
    roles = session.exec(select(Role)).all()
    return roles


@router.get(
    "/permissions",
    response_model=List[PermissionPublic],
    dependencies=[require_permission("users", "read")],
    summary="List all available system permissions",
)
def get_all_permissions(session: SessionDep):
    """Retrieve all base permissions available in the system."""
    permissions = session.exec(select(Permission)).all()
    return permissions
