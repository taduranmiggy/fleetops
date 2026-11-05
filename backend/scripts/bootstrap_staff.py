#!/usr/bin/env python3
"""Create or reset the demo staff accounts in the configured database.

Set BOOTSTRAP_STAFF_PASSWORD only for the one-time Railway Console run, then
remove it from the service variables.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.entities import User, UserRole


STAFF_ACCOUNTS = (
    ("admin@fleetops.com", "FleetOps Admin", UserRole.ADMIN),
    ("manager@fleetops.com", "FleetOps Manager", UserRole.MANAGER),
    ("dispatcher@fleetops.com", "FleetOps Dispatcher", UserRole.DISPATCHER),
    ("helper1@fleetops.com", "FleetOps Helper", UserRole.HELPER),
)


def main() -> None:
    password = os.environ.get("BOOTSTRAP_STAFF_PASSWORD", "")
    if len(password) < 8:
        raise SystemExit(
            "BOOTSTRAP_STAFF_PASSWORD must be set temporarily and contain at least 8 characters."
        )

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    password_hash = hash_password(password)
    with Session(engine) as db:
        for email, full_name, role in STAFF_ACCOUNTS:
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                user = User(email=email, full_name=full_name, role=role)
                db.add(user)
            user.full_name = full_name
            user.role = role
            user.password_hash = password_hash
            user.failed_login_count = 0
            user.locked_until = None
        db.commit()

    print("Staff accounts created or updated:")
    for email, _, role in STAFF_ACCOUNTS:
        print(f"  {role.value}: {email}")
    print("Remove BOOTSTRAP_STAFF_PASSWORD from Railway Variables now.")


if __name__ == "__main__":
    main()
