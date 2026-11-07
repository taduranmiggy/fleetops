"""Add database defaults for raw inserts into capacity resource tables."""

from alembic import op
import sqlalchemy as sa


revision = "20261107_0006_capacity_defaults"
down_revision = "20261107_0005_capacity_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "availability_status",
        existing_type=sa.String(length=32),
        existing_nullable=False,
        server_default=sa.text("'available'"),
    )
    op.alter_column(
        "users",
        "failed_login_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("0"),
    )
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(),
        existing_nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    for column, column_type, default in (
        ("status", sa.String(length=50), "'available'"),
        ("availability_status", sa.String(length=32), "'available'"),
        ("fuel_efficiency_kmpl", sa.Float(), "4.0"),
        ("odometer_km", sa.Float(), "0.0"),
        ("age_years", sa.Float(), "1.0"),
        ("vehicle_class", sa.String(length=32), "'Class 3'"),
    ):
        op.alter_column(
            "trucks",
            column,
            existing_type=column_type,
            existing_nullable=False,
            server_default=sa.text(default),
        )


def downgrade() -> None:
    op.alter_column(
        "users",
        "availability_status",
        existing_type=sa.String(length=32),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "users",
        "failed_login_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(),
        existing_nullable=False,
        server_default=None,
    )
    for column, column_type in (
        ("status", sa.String(length=50)),
        ("availability_status", sa.String(length=32)),
        ("fuel_efficiency_kmpl", sa.Float()),
        ("odometer_km", sa.Float()),
        ("age_years", sa.Float()),
        ("vehicle_class", sa.String(length=32)),
    ):
        op.alter_column(
            "trucks",
            column,
            existing_type=column_type,
            existing_nullable=False,
            server_default=None,
        )
