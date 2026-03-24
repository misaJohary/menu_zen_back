"""
Reusable FastAPI permission dependency factory.

Usage in a router:

    from app.cores.permissions import require_permission

    # As a route-level dependency (no access to the return value):
    @router.get("/orders", dependencies=[require_permission("orders", "read")])
    def read_orders(...):
        ...

    # As an injected dependency (when you need it inline):
    @router.post("/orders")
    def create_order(
        _: None = require_permission("orders", "create"),
        ...
    ):
        ...
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.configs.database_configs import get_session
from app.models.models import User
from app.services import permission_service
from app.services.auth_service import get_current_active_user
from sqlmodel import Session


def require_permission(resource: str, action: str) -> Depends:
    """Return a FastAPI ``Depends`` that enforces ``resource:action`` access.

    Raises HTTP 403 if the authenticated user does not hold the permission.
    super_admin always passes.

    Args:
        resource: The resource name, e.g. ``"orders"``, ``"menu"``.
        action:   The action name,   e.g. ``"read"``, ``"create"``.

    Returns:
        A ``Depends(...)`` object ready to be used in ``dependencies=[...]``
        or as a default-argument annotation.
    """

    def _check_permission(
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[Session, Depends(get_session)],
    ) -> None:
        allowed = permission_service.can(current_user, resource, action, db)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not allowed: {resource}:{action}",
            )

    # Give the inner function a unique name so FastAPI doesn't de-duplicate
    # identical dependency signatures across different require_permission calls.
    _check_permission.__name__ = f"_require_{resource}_{action}"

    return Depends(_check_permission)
