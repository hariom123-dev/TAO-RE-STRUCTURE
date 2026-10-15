"""
TAO Authentication & RBAC Module.
"""

from backend.auth.rbac import (
    RBACManager,
    UserProfile,
    UserRole,
    rbac_manager,
    require_role,
)

__all__ = [
    "RBACManager",
    "UserProfile",
    "UserRole",
    "rbac_manager",
    "require_role",
]
