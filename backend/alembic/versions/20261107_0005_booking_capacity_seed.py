"""Seed the minimum operational crew and fleet for fresh booking databases."""

from alembic import op
import sqlalchemy as sa


revision = "20261107_0005_capacity_seed"
down_revision = "20260714_0004_delivery_verify"
branch_labels = None
depends_on = None


def _insert_if_missing(table: sa.Table, key_column: str, values: dict) -> None:
    bind = op.get_bind()
    if bind.execute(
        sa.select(table.c[key_column]).where(table.c[key_column] == values[key_column])
    ).first() is None:
        op.bulk_insert(table, [values])


def upgrade() -> None:
    users = sa.table(
        "users",
        sa.column("email", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("full_name", sa.String),
        sa.column("role", sa.String),
        sa.column("availability_status", sa.String),
    )
    for email, name, role in (
        ("driver1@fleetops.com", "Fleet Driver 1", "driver"),
        ("driver2@fleetops.com", "Fleet Driver 2", "driver"),
        ("helper1@fleetops.com", "Fleet Helper 1", "helper"),
        ("helper2@fleetops.com", "Fleet Helper 2", "helper"),
    ):
        _insert_if_missing(
            users,
            "email",
            {
                "email": email,
                "password_hash": None,
                "full_name": name,
                "role": role,
                "availability_status": "available",
            },
        )

    trucks = sa.table(
        "trucks",
        sa.column("code", sa.String),
        sa.column("capacity_tons", sa.Float),
        sa.column("status", sa.String),
        sa.column("availability_status", sa.String),
    )
    for code, capacity in (
        ("TRK-001", 42),
        ("TRK-002", 42),
        ("TRK-003", 42),
        ("TRK-004", 42),
    ):
        _insert_if_missing(
            trucks,
            "code",
            {
                "code": code,
                "capacity_tons": capacity,
                "status": "available",
                "availability_status": "available",
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM users WHERE email IN "
            "('driver1@fleetops.com','driver2@fleetops.com','helper1@fleetops.com','helper2@fleetops.com')"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM trucks WHERE code IN ('TRK-001','TRK-002','TRK-003','TRK-004')"
        )
    )
