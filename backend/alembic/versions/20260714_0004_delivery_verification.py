"""Add booking-level delivery verification credentials and audit fields."""

from alembic import op
import sqlalchemy as sa


# Alembic's default `alembic_version.version_num` column is VARCHAR(32).
# Keep revision identifiers within that limit so MySQL can record upgrades.
revision = "20260714_0004_delivery_verify"
down_revision = "20260607_0003_toll_plaza_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("bookings")}
    additions = {
        "delivery_verification_token": sa.Column("delivery_verification_token", sa.String(length=64), nullable=True),
        "delivery_verification_code": sa.Column("delivery_verification_code", sa.String(length=16), nullable=True),
        "delivery_verification_created_at": sa.Column("delivery_verification_created_at", sa.DateTime(), nullable=True),
        "delivery_verification_used_at": sa.Column("delivery_verification_used_at", sa.DateTime(), nullable=True),
        "delivery_verification_used_by_helper_id": sa.Column(
            "delivery_verification_used_by_helper_id", sa.Integer(), nullable=True
        ),
        "delivery_verification_method": sa.Column("delivery_verification_method", sa.String(length=16), nullable=True),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("bookings", column)

    inspector = sa.inspect(op.get_bind())
    foreign_keys = {fk.get("name") for fk in inspector.get_foreign_keys("bookings")}
    index_rows = inspector.get_indexes("bookings")
    unique_rows = inspector.get_unique_constraints("bookings")
    indexes = {idx["name"] for idx in index_rows}
    unique_constraints = {item.get("name") for item in unique_rows}
    unique_column_sets = {
        tuple(item.get("column_names") or [])
        for item in [*index_rows, *unique_rows]
        if item.get("unique", True)
    }
    if "fk_bookings_delivery_verification_helper" not in foreign_keys:
        op.create_foreign_key(
            "fk_bookings_delivery_verification_helper",
            "bookings",
            "users",
            ["delivery_verification_used_by_helper_id"],
            ["id"],
        )
    if (
        "uq_bookings_delivery_verification_token" not in indexes | unique_constraints
        and ("delivery_verification_token",) not in unique_column_sets
    ):
        op.create_unique_constraint(
            "uq_bookings_delivery_verification_token", "bookings", ["delivery_verification_token"]
        )
    if (
        "uq_bookings_delivery_verification_code" not in indexes | unique_constraints
        and ("delivery_verification_code",) not in unique_column_sets
    ):
        op.create_unique_constraint(
            "uq_bookings_delivery_verification_code", "bookings", ["delivery_verification_code"]
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    foreign_keys = {fk.get("name") for fk in inspector.get_foreign_keys("bookings")}
    indexes = {idx["name"] for idx in inspector.get_indexes("bookings")}
    unique_constraints = {item.get("name") for item in inspector.get_unique_constraints("bookings")}
    if "uq_bookings_delivery_verification_code" in indexes | unique_constraints:
        op.drop_constraint("uq_bookings_delivery_verification_code", "bookings", type_="unique")
    if "uq_bookings_delivery_verification_token" in indexes | unique_constraints:
        op.drop_constraint("uq_bookings_delivery_verification_token", "bookings", type_="unique")
    if "fk_bookings_delivery_verification_helper" in foreign_keys:
        op.drop_constraint("fk_bookings_delivery_verification_helper", "bookings", type_="foreignkey")
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("bookings")}
    for name in (
        "delivery_verification_method",
        "delivery_verification_used_by_helper_id",
        "delivery_verification_used_at",
        "delivery_verification_created_at",
        "delivery_verification_code",
        "delivery_verification_token",
    ):
        if name in columns:
            op.drop_column("bookings", name)
