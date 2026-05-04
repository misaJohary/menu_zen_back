from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app.configs.auth_configs import settings
from app.configs.database_configs import create_db_and_tables, engine
from app.models.models import (
    Permission,
    Role,
    RolePermission,
    User,
)
from app.routers import (
    auth,
    categories,
    kitchens,
    languages,
    menu,
    menu_items,
    orders,
    restaurant,
    restaurant_table,
    stats,
    ws_connect,
)
from app.routers import admin_permissions
from app.services.auth_service import get_password_hash

import uvicorn


# ── RBAC seed data ─────────────────────────────────────────────────────────────

_ROLES: list[dict] = [
    {"name": "super_admin", "level": 100},
    {"name": "admin",       "level": 80},
    {"name": "cashier",     "level": 40},
    {"name": "server",      "level": 30},
    {"name": "cook",        "level": 20},
]

_ALL_PERMISSIONS: list[tuple[str, str]] = [
    ("users",    "create"),
    ("users",    "read"),
    ("users",    "update"),
    ("menu",     "create"),
    ("menu",     "read"),
    ("menu",     "update"),
    ("menu",     "delete"),
    ("orders",   "create"),
    ("orders",   "read"),
    ("orders",   "update"),
    ("orders",   "delete"),
    ("payments", "create"),
    ("payments", "read"),
    ("tables",   "manage"),
    ("tables",   "read"),
    ("tables",   "update"),
    ("tables",   "reset"),
    ("reports",  "read"),
    ("kitchens", "create"),
    ("kitchens", "read"),
    ("kitchens", "update"),
    ("kitchens", "delete"),
    ("messages",      "read"),
    ("messages",      "create"),
    ("messages",      "delete"),
    ("conversations", "create"),
    ("conversations", "read"),
    ("conversations", "update"),
    ("calls",         "create"),
    ("calls",         "read"),
]

_ROLE_PERMISSIONS: dict[str, list[tuple[str, str]]] = {
    "super_admin": _ALL_PERMISSIONS,
    "admin": [
        ("users",    "create"), ("users",    "read"),   ("users",    "update"),
        ("menu",     "create"), ("menu",     "read"),   ("menu",     "update"), ("menu", "delete"),
        ("orders",   "create"), ("orders",   "read"),   ("orders",   "update"), ("orders", "delete"),
        ("payments", "create"), ("payments", "read"),
        ("tables",   "manage"), ("tables",   "read"),   ("tables",   "update"), ("tables", "reset"),
        ("reports",  "read"),
        ("kitchens", "create"), ("kitchens", "read"), ("kitchens", "update"), ("kitchens", "delete"),
        ("messages", "read"), ("messages", "create"), ("messages", "delete"),
        ("conversations", "create"), ("conversations", "read"), ("conversations", "update"),
        ("calls", "create"), ("calls", "read"),
    ],
    "cashier": [
        ("menu",     "read"),
        ("orders",   "create"), ("orders",  "read"),    ("orders",   "update"),
        ("payments", "create"), ("payments","read"),
        ("tables",   "read"),
        ("messages", "read"), ("messages", "create"), ("messages", "delete"),
        ("conversations", "create"), ("conversations", "read"), ("conversations", "update"),
        ("calls", "create"), ("calls", "read"),
    ],
    "server": [
        ("menu", "create"), ("menu", "read"),
        ("orders", "create"), ("orders", "read"), ("orders", "update"), ("orders", "delete"),
        ("tables", "manage"), ("tables", "read"), ("tables", "update"),
        ("payments", "read"),
        ("kitchens", "read"),
        ("messages", "read"), ("messages", "create"), ("messages", "delete"),
        ("conversations", "create"), ("conversations", "read"), ("conversations", "update"),
        ("calls", "create"), ("calls", "read"),
    ],
    "cook": [
        ("menu",     "read"),
        ("orders",   "read"),
        ("tables",   "read"),
        ("kitchens", "read"),
        ("messages", "read"), ("messages", "create"), ("messages", "delete"),
        ("conversations", "create"), ("conversations", "read"), ("conversations", "update"),
        ("calls", "create"), ("calls", "read"),
    ],
}


def seed_rbac(session: Session) -> None:
    """Seed roles, permissions, and role→permission links if they don't exist yet.

    This function is idempotent: it will not create duplicates on subsequent
    startups. It uses INSERT-if-missing logic rather than checking the entire
    table count, so partial seeds are also safe to complete.
    """
    # ── Roles ──────────────────────────────────────────────────────────────────
    role_map: dict[str, Role] = {}
    for role_data in _ROLES:
        existing = session.exec(
            select(Role).where(Role.name == role_data["name"])
        ).first()
        if existing is None:
            existing = Role(name=role_data["name"], level=role_data["level"])
            session.add(existing)
            session.flush()  # get the generated id without committing yet
            print(f"[seed] Created role: {role_data['name']} (level={role_data['level']})")
        role_map[role_data["name"]] = existing

    # ── Permissions ────────────────────────────────────────────────────────────
    perm_map: dict[tuple[str, str], Permission] = {}
    for resource, action in _ALL_PERMISSIONS:
        existing = session.exec(
            select(Permission).where(
                Permission.resource == resource,
                Permission.action == action,
            )
        ).first()
        if existing is None:
            existing = Permission(resource=resource, action=action)
            session.add(existing)
            session.flush()
            print(f"[seed] Created permission: {resource}:{action}")
        perm_map[(resource, action)] = existing

    # ── Role → Permission links ────────────────────────────────────────────────
    for role_name, perms in _ROLE_PERMISSIONS.items():
        role = role_map.get(role_name)
        if role is None:
            continue
        for resource, action in perms:
            perm = perm_map.get((resource, action))
            if perm is None:
                continue
            existing_link = session.exec(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                )
            ).first()
            if existing_link is None:
                session.add(RolePermission(role_id=role.id, permission_id=perm.id))

    session.commit()
    print("[seed] RBAC seed complete.")


def seed_super_admin(session: Session) -> None:
    """Auto-create a super admin user from environment variables if none exists.

    Required env vars (set in .env):
        SUPER_ADMIN_EMAIL
        SUPER_ADMIN_PASSWORD
        SUPER_ADMIN_USERNAME (optional)

    The created account has must_change_password=True and disabled=False.
    """
    email = settings.super_admin_email
    password = settings.super_admin_password

    if not email or not password:
        print(
            "[seed] SUPER_ADMIN_EMAIL or SUPER_ADMIN_PASSWORD not set in Settings — "
            "skipping super admin creation."
        )
        return

    username = settings.super_admin_username or "super_admin"

    # Find the super_admin role (must have been seeded already)
    super_role = session.exec(
        select(Role).where(Role.name == "super_admin")
    ).first()
    if super_role is None:
        print("[seed] WARNING: super_admin role not found — skipping super admin creation.")
        return

    # Check if a super_admin user already exists
    existing = session.exec(
        select(User).where(User.role_id == super_role.id)
    ).first()
    if existing is not None:
        print(f"[seed] Super admin already exists (username={existing.username}) — skipping.")
        return

    super_admin = User(
        username=username,
        email=email,
        full_name="Super Administrator",
        disabled=False,
        role_id=super_role.id,
        hashed_psd=get_password_hash(password),
        must_change_password=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    session.add(super_admin)
    session.commit()
    session.refresh(super_admin)
    print(f"[seed] Super admin created: username='{username}', email='{email}'")


# ── App lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application starting up...")
    # 1. Ensure all tables exist (needed because migrations are incomplete)
    create_db_and_tables()
    
    # 2. Seed RBAC data and super admin
    with Session(engine) as session:
        seed_rbac(session)
        seed_super_admin(session)
    yield
    print("Application shutting down...")


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(restaurant.router)
app.include_router(menu.router)
app.include_router(categories.router)
app.include_router(kitchens.router)
app.include_router(menu_items.router)
app.include_router(orders.router)
app.include_router(restaurant_table.router)
app.include_router(languages.router)
app.include_router(ws_connect.router)
app.include_router(stats.router)
app.include_router(admin_permissions.router)   # ← new RBAC admin router


@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)