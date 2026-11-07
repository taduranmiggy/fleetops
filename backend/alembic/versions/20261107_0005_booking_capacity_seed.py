"""Seed the minimum operational crew and fleet for fresh booking databases."""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "20261107_0005_capacity_seed"
down_revision = "20260714_0004_delivery_verify"
branch_labels = None
depends_on = None


MARKER_TABLE = "fleetops_capacity_seed_rows"


def _insert_if_missing(
    table: sa.Table,
    key_column: str,
    values: dict,
    marker_key: str,
    marker_table: sa.Table,
) -> None:
    bind = op.get_bind()
    existing = bind.execute(
        sa.select(table.c[key_column]).where(table.c[key_column] == values[key_column])
    ).first()
    if existing is not None:
        return
    op.bulk_insert(table, [values])
    op.bulk_insert(
        marker_table,
        [{"resource_type": table.name, "resource_key": marker_key}],
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(MARKER_TABLE):
        op.create_table(
            MARKER_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("resource_type", sa.String(length=32), nullable=False),
            sa.Column("resource_key", sa.String(length=255), nullable=False),
            sa.UniqueConstraint("resource_type", "resource_key", name="uq_capacity_seed_resource"),
        )

    users = sa.table(
        "users",
        sa.column("email", sa.String(length=255)),
        sa.column("password_hash", sa.String(length=255)),
        sa.column("full_name", sa.String(length=255)),
        sa.column("role", sa.String(length=32)),
        sa.column("availability_status", sa.String(length=32)),
        sa.column("failed_login_count", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
    )
    markers = sa.table(
        MARKER_TABLE,
        sa.column("resource_type", sa.String(length=32)),
        sa.column("resource_key", sa.String(length=255)),
    )
    now = datetime.utcnow()
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
                "failed_login_count": 0,
                "created_at": now,
            },
            email,
            markers,
        )

    trucks = sa.table(
        "trucks",
        sa.column("code", sa.String(length=50)),
        sa.column("model_name", sa.String(length=255)),
        sa.column("capacity_tons", sa.Float()),
        sa.column("status", sa.String(length=50)),
        sa.column("availability_status", sa.String(length=32)),
        sa.column("fuel_efficiency_kmpl", sa.Float()),
        sa.column("odometer_km", sa.Float()),
        sa.column("age_years", sa.Float()),
        sa.column("vehicle_class", sa.String(length=32)),
    )
    for code in ("TRK-001", "TRK-002", "TRK-003", "TRK-004"):
        _insert_if_missing(
            trucks,
            "code",
            {
                "code": code,
                "model_name": "Fleet Truck",
                "capacity_tons": 42.0,
                "status": "available",
                "availability_status": "available",
                "fuel_efficiency_kmpl": 4.0,
                "odometer_km": 0.0,
                "age_years": 1.0,
                "vehicle_class": "Class 3",
            },
            code,
            markers,
        )


def downgrade() -> None:
    bind = op.get_bind()
    markers = sa.table(
        MARKER_TABLE,
        sa.column("resource_type", sa.String(length=32)),
        sa.column("resource_key", sa.String(length=255)),
    )
    for resource_type, table_name, key_column in (
        ("users", "users", "email"),
        ("trucks", "trucks", "code"),
    ):
        keys = [
            row[0]
            for row in bind.execute(
                sa.select(markers.c.resource_key).where(
                    markers.c.resource_type == resource_type
                )
            ).all()
        ]
        if keys:
            table = sa.table(table_name, sa.column(key_column, sa.String(length=255)))
            bind.execute(table.delete().where(table.c[key_column].in_(keys)))
    op.drop_table(MARKER_TABLE)
