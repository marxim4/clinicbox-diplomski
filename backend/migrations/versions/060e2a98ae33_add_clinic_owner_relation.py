"""Add clinic owner relation

Revision ID: 060e2a98ae33
Revises: 9ccb28bfe5df
Create Date: 2025-11-24 18:14:08.137325
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "060e2a98ae33"
down_revision = "9ccb28bfe5df"
branch_labels = None
depends_on = None


def upgrade():
    # Category: per-clinic unique category names
    with op.batch_alter_table("category") as batch_op:
        batch_op.create_unique_constraint(
            "uq_category_clinic_name",
            ["clinic_id", "name"]
        )

    # Clinic: add owner_user_id
    with op.batch_alter_table("clinic") as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_clinic_owner_user_id",
            ["owner_user_id"]
        )
        batch_op.create_foreign_key(
            "fk_clinic_owner_user",
            "user",
            ["owner_user_id"],
            ["user_id"]
        )

    # Payment: add doctor_id
    with op.batch_alter_table("payment") as batch_op:
        batch_op.add_column(sa.Column("doctor_id", sa.Integer(), nullable=False))
        batch_op.create_foreign_key(
            "fk_payment_doctor",
            "user",
            ["doctor_id"],
            ["user_id"]
        )


def downgrade():
    # Payment
    with op.batch_alter_table("payment") as batch_op:
        batch_op.drop_column("doctor_id")

    # Clinic
    with op.batch_alter_table("clinic") as batch_op:
        batch_op.drop_column("owner_user_id")

    # Category
    with op.batch_alter_table("category") as batch_op:
        batch_op.drop_constraint(
            "uq_category_clinic_name",
            type_="unique"
        )
