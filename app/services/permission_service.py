"""
Permission resolution service for the RBAC system.

Resolution order:
  1. super_admin role → always permitted (bypass)
  2. Load all permissions attached to the user's role via role_permissions
  3. Apply user-level overrides from user_permissions:
       - type="grant"  → add to the set
       - type="revoke" → remove from the set
  4. Cache the resolved frozenset per user_id for PERMISSION_CACHE_TTL_SECONDS.

Call `invalidate_cache(user_id)` whenever a user's overrides are changed.
"""

import time
from typing import Dict, Optional, Tuple
from sqlmodel import Session, select

from app.models.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserPermission,
    UserPermissionType,
)

# ── Cache ─────────────────────────────────────────────────────────────────────

PERMISSION_CACHE_TTL_SECONDS: int = 300  # 5 minutes

# Structure: { user_id: (resolved_set, expiry_timestamp) }
_cache: Dict[int, Tuple[frozenset, float]] = {}

SUPER_ADMIN_ROLE_NAME = "super_admin"


# ── Cache helpers ─────────────────────────────────────────────────────────────

def invalidate_cache(user_id: int) -> None:
    """Remove a user's resolved-permission entry from the cache.

    Call this whenever user_permissions rows are created, updated, or deleted,
    or when a user's role_id changes.
    """
    _cache.pop(user_id, None)


def _cache_get(user_id: int) -> Optional[frozenset]:
    entry = _cache.get(user_id)
    if entry is None:
        return None
    resolved, expiry = entry
    if time.monotonic() > expiry:
        # Expired — evict
        _cache.pop(user_id, None)
        return None
    return resolved


def _cache_set(user_id: int, resolved: frozenset) -> None:
    _cache[user_id] = (resolved, time.monotonic() + PERMISSION_CACHE_TTL_SECONDS)


# ── Core resolution ───────────────────────────────────────────────────────────

def _load_role_name(user: User, db: Session) -> Optional[str]:
    """Return the name of the user's role, or None if the user has no role."""
    if user.role_id is None:
        return None
    role = db.get(Role, user.role_id)
    return role.name if role else None


def resolve_permissions(user: User, db: Session) -> frozenset:
    """Return the full set of permitted 'resource:action' strings for a user.

    Checks the in-memory cache first. On a cache miss, loads from the DB,
    applies user-level overrides, and stores the result.

    super_admin is represented as the sentinel frozenset {"*"} — callers
    should treat this as "all permissions allowed".
    """
    if user.id is None:
        return frozenset()

    # ── 1. Cache hit ──────────────────────────────────────────────────────────
    cached = _cache_get(user.id)
    if cached is not None:
        return cached

    # ── 2. Super-admin bypass ─────────────────────────────────────────────────
    role_name = _load_role_name(user, db)
    if role_name == SUPER_ADMIN_ROLE_NAME:
        sentinel = frozenset({"*"})
        _cache_set(user.id, sentinel)
        return sentinel

    # ── 3. Load role permissions ──────────────────────────────────────────────
    role_perms: set[str] = set()
    if user.role_id is not None:
        stmt = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == user.role_id)
        )
        permissions = db.exec(stmt).all()
        role_perms = {f"{p.resource}:{p.action}" for p in permissions}

    # ── 4. Apply user-level overrides ─────────────────────────────────────────
    overrides_stmt = select(UserPermission).where(UserPermission.user_id == user.id)
    overrides = db.exec(overrides_stmt).all()

    for override in overrides:
        perm = db.get(Permission, override.permission_id)
        if perm is None:
            continue
        key = f"{perm.resource}:{perm.action}"
        if override.type == UserPermissionType.GRANT:
            role_perms.add(key)
        elif override.type == UserPermissionType.REVOKE:
            role_perms.discard(key)

    resolved = frozenset(role_perms)
    _cache_set(user.id, resolved)
    return resolved


# ── Public check API ──────────────────────────────────────────────────────────

def can(user: User, resource: str, action: str, db: Session) -> bool:
    """Return True if the user is allowed to perform `action` on `resource`.

    super_admin always returns True regardless of the permission matrix.
    """
    resolved = resolve_permissions(user, db)

    # Sentinel value used for super_admin
    if "*" in resolved:
        return True

    return f"{resource}:{action}" in resolved


def get_user_permission_details(user: User, db: Session) -> list[dict]:
    """Return all known permissions with their status for `user`.

    Each entry has the shape:
        {
            "permission_id": int,
            "resource": str,
            "action": str,
            "status": "from_role" | "granted" | "revoked" | "none",
        }

    Used by the admin endpoints (GET /admin/users/{user_id}/permissions).
    """
    # All permissions in the system
    all_perms = db.exec(select(Permission)).all()

    # Role permissions for this user
    role_perm_ids: set[int] = set()
    if user.role_id is not None:
        rp_stmt = select(RolePermission).where(RolePermission.role_id == user.role_id)
        role_perm_ids = {rp.permission_id for rp in db.exec(rp_stmt).all()}

    # User overrides
    overrides_stmt = select(UserPermission).where(UserPermission.user_id == user.id)
    overrides: dict[int, UserPermissionType] = {
        ov.permission_id: ov.type for ov in db.exec(overrides_stmt).all()
    }

    result = []
    for perm in all_perms:
        if perm.id in overrides:
            ov_type = overrides[perm.id]
            status = "granted" if ov_type == UserPermissionType.GRANT else "revoked"
        elif perm.id in role_perm_ids:
            status = "from_role"
        else:
            status = "none"

        result.append(
            {
                "permission_id": perm.id,
                "resource": perm.resource,
                "action": perm.action,
                "status": status,
            }
        )

    return result
