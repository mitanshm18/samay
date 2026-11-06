"""Saved bills and calculation runs, append-only (decision 0005).

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-07

Written by hand. Money is BIGINT paise; NULL means MISSING (never 0).
A trigger refuses UPDATE, DELETE and TRUNCATE on both tables.
The downgrade refuses to run while any record is saved.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256_HEX = "'^[0-9a-f]{64}$'"
TABLES = ("bill_document", "calculation_run")


def upgrade() -> None:
    op.create_table(
        "bill_document",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bill_id", sa.Text(), nullable=False),
        sa.Column("tariff_id", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("source_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("source_sha256", sa.CHAR(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bill_document"),
        sa.UniqueConstraint("source_sha256", name="uq_bill_document_source_sha256"),
        sa.CheckConstraint("format = 'samay.bill/1'", name="ck_bill_document_format"),
        sa.CheckConstraint(f"source_sha256 ~ {SHA256_HEX}", name="ck_bill_document_source_sha256"),
        sa.CheckConstraint(
            "octet_length(source_bytes) > 0", name="ck_bill_document_source_not_empty"
        ),
        sa.CheckConstraint("length(bill_id) > 0", name="ck_bill_document_bill_id_not_empty"),
    )
    op.create_table(
        "calculation_run",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bill_document_id", sa.BigInteger(), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("tariff_id", sa.Text(), nullable=False),
        sa.Column("tariff_name", sa.Text(), nullable=False),
        sa.Column("tariff_status", sa.Text(), nullable=False),
        sa.Column("exit_code", sa.SmallInteger(), nullable=False),
        sa.Column("report_format", sa.Text(), nullable=False),
        sa.Column("report_text", sa.Text(), nullable=False),
        sa.Column("report_sha256", sa.CHAR(64), nullable=False),
        sa.Column("calculated_total_paise", sa.BigInteger(), nullable=True),
        sa.Column("printed_total_paise", sa.BigInteger(), nullable=True),
        sa.Column("total_difference_paise", sa.BigInteger(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calculation_run"),
        sa.ForeignKeyConstraint(
            ["bill_document_id"],
            ["bill_document.id"],
            name="fk_calculation_run_bill_document_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "command IN ('calculate', 'reconcile')", name="ck_calculation_run_command"
        ),
        sa.CheckConstraint(
            "report_format = 'samay.report/1'", name="ck_calculation_run_report_format"
        ),
        sa.CheckConstraint(
            "tariff_status IN ('synthetic', 'verified')",
            name="ck_calculation_run_tariff_status",
        ),
        sa.CheckConstraint(
            f"report_sha256 ~ {SHA256_HEX}", name="ck_calculation_run_report_sha256"
        ),
        sa.CheckConstraint(
            "(command = 'calculate' AND exit_code = 0)"
            " OR (command = 'reconcile' AND exit_code IN (0, 1))",
            name="ck_calculation_run_exit_code",
        ),
        sa.CheckConstraint(
            "explanation IS NULL OR explanation IN ('complete', 'partial', 'undeterminable')",
            name="ck_calculation_run_explanation_value",
        ),
        sa.CheckConstraint(
            "(command = 'calculate' AND explanation IS NULL AND printed_total_paise IS NULL"
            " AND total_difference_paise IS NULL)"
            " OR (command = 'reconcile' AND explanation IS NOT NULL)",
            name="ck_calculation_run_reconcile_fields",
        ),
        sa.CheckConstraint(
            "(printed_total_paise IS NOT NULL AND calculated_total_paise IS NOT NULL"
            " AND total_difference_paise IS NOT NULL"
            " AND total_difference_paise = printed_total_paise - calculated_total_paise)"
            " OR ((printed_total_paise IS NULL OR calculated_total_paise IS NULL)"
            " AND total_difference_paise IS NULL)",
            name="ck_calculation_run_total_difference",
        ),
    )
    op.create_index("ix_calculation_run_bill_document_id", "calculation_run", ["bill_document_id"])
    op.execute(
        """
        CREATE FUNCTION samay_refuse_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'SAMAY saved records are immutable: % on % refused',
                TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$
        """
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION samay_refuse_change()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION samay_refuse_change()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    for table in TABLES:
        count = connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError(
                f"refusing to downgrade: {table} holds {count} saved record(s). "
                "Saved results are never deleted by a migration."
            )
    op.drop_table("calculation_run")
    op.drop_table("bill_document")
    op.execute("DROP FUNCTION samay_refuse_change()")
