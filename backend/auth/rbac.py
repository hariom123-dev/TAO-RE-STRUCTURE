"""
Multi-Tenant Organization & Role-Based Access Control (RBAC) Gateway.
Lightweight SQLite-backed identity, permission, and API-key management.

Roles:
- Viewer: Metrics, telemetry, receipts, and audit reports.
- Developer: Query execution, counterfactual forks, and test evaluations.
- SecurityOfficer: Red-team attacks, debate deadlock approvals, stego inspection.
- Admin: Constitutional rules management, SIEM webhook subscriptions, user management.
"""

import os
import sqlite3
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Optional
from fastapi import Header, HTTPException, status
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    VIEWER = "viewer"
    DEVELOPER = "developer"
    SECURITY_OFFICER = "security_officer"
    ADMIN = "admin"


# Role priority ordering (higher number = greater privilege)
ROLE_HIERARCHY = {
    UserRole.VIEWER: 1,
    UserRole.DEVELOPER: 2,
    UserRole.SECURITY_OFFICER: 3,
    UserRole.ADMIN: 4,
}


class UserProfile(BaseModel):
    user_id: str
    org_id: str
    email: str
    role: UserRole
    api_key: str
    created_at: float = Field(default_factory=time.time)


class RBACManager:
    """Manages multi-tenant organizations, API keys, and role permissions."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            state_dir = Path(__file__).parent.parent / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(state_dir / "rbac.sqlite")
        else:
            self.db_path = db_path

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS organizations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL,
                    api_key TEXT UNIQUE NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(org_id) REFERENCES organizations(id)
                );
            """)

            # Bootstrap default organization and admin if table empty
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM organizations")
            if cursor.fetchone()[0] == 0:
                default_org_id = "org_default"
                cursor.execute(
                    "INSERT INTO organizations (id, name, created_at) VALUES (?, ?, ?)",
                    (default_org_id, "Default Enterprise Org", time.time()),
                )
                # Seed standard tiered test keys
                seeds = [
                    ("usr_admin", default_org_id, "admin@tao.local", UserRole.ADMIN.value, "tao-key-admin-production-root"),
                    ("usr_secops", default_org_id, "secops@tao.local", UserRole.SECURITY_OFFICER.value, "tao-key-secops-oversight"),
                    ("usr_dev", default_org_id, "dev@tao.local", UserRole.DEVELOPER.value, "tao-key-dev-engineering"),
                    ("usr_viewer", default_org_id, "auditor@tao.local", UserRole.VIEWER.value, "tao-key-viewer-telemetry"),
                ]
                for uid, oid, email, role, key in seeds:
                    cursor.execute(
                        "INSERT OR IGNORE INTO users (id, org_id, email, role, api_key, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (uid, oid, email, role, key, time.time()),
                    )
            conn.commit()

    def create_user(self, org_id: str, email: str, role: UserRole) -> UserProfile:
        api_key = f"tao-key-{uuid.uuid4().hex}"
        uid = f"usr_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO users (id, org_id, email, role, api_key, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, org_id, email, role.value, api_key, now),
            )
            conn.commit()
        return UserProfile(
            user_id=uid,
            org_id=org_id,
            email=email,
            role=role,
            api_key=api_key,
            created_at=now,
        )

    def get_user_by_api_key(self, api_key: str) -> Optional[UserProfile]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, org_id, email, role, api_key, created_at FROM users WHERE api_key = ?", (api_key,))
            row = cursor.fetchone()
            if row:
                return UserProfile(
                    user_id=row["id"],
                    org_id=row["org_id"],
                    email=row["email"],
                    role=UserRole(row["role"]),
                    api_key=row["api_key"],
                    created_at=row["created_at"],
                )
        return None

    def list_users(self, org_id: Optional[str] = None) -> list[UserProfile]:
        users = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if org_id:
                cursor.execute("SELECT id, org_id, email, role, api_key, created_at FROM users WHERE org_id = ?", (org_id,))
            else:
                cursor.execute("SELECT id, org_id, email, role, api_key, created_at FROM users")
            for row in cursor.fetchall():
                users.append(UserProfile(
                    user_id=row["id"],
                    org_id=row["org_id"],
                    email=row["email"],
                    role=UserRole(row["role"]),
                    api_key=row["api_key"],
                    created_at=row["created_at"],
                ))
        return users


rbac_manager = RBACManager()


def require_role(min_role: UserRole):
    """
    FastAPI dependency verifying caller has sufficient role privilege.
    Supports Authorization Bearer tokens and X-TAO-API-Key.
    Falls back to a default Developer/Admin identity if no credentials supplied,
    preserving local dev convenience and backwards compatibility.
    """
    def dependency(
        authorization: Optional[str] = Header(None),
        x_tao_api_key: Optional[str] = Header(None, alias="X-TAO-API-Key"),
    ) -> UserProfile:
        token = x_tao_api_key
        if not token and authorization:
            if authorization.startswith("Bearer "):
                token = authorization[7:].strip()
            else:
                token = authorization.strip()

        # Permissive local development fallback
        if not token:
            return UserProfile(
                user_id="usr_local_dev",
                org_id="org_default",
                email="developer@tao.local",
                role=UserRole.ADMIN,
                api_key="local-dev-session-key",
            )

        user = rbac_manager.get_user_by_api_key(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid TAO API key or token supplied.",
            )

        if ROLE_HIERARCHY[user.role] < ROLE_HIERARCHY[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: Action requires {min_role.value.upper()} role, but you are {user.role.value.upper()}.",
            )

        return user

    return dependency
