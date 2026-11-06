"""The two tables (decision 0005). Both are append-only: a trigger in the
migration refuses UPDATE, DELETE and TRUNCATE, so a saved result can never be
changed. Checking a bill again adds a new run.

Money columns are BIGINT paise. NULL means the value is MISSING (or, for the
printed total, not given); it is never written as 0. The exact report text is
the record; the paise columns are a copy of its totals for listing, checked
against the report before saving and by CHECK constraints here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    LargeBinary,
    MetaData,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

SHA256_HEX = "'^[0-9a-f]{64}$'"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class BillDocument(Base):
    """One bill file exactly as received. The same bytes are stored once."""

    __tablename__ = "bill_document"
    __table_args__ = (
        CheckConstraint("format = 'samay.bill/1'", name="format"),
        CheckConstraint(f"source_sha256 ~ {SHA256_HEX}", name="source_sha256"),
        CheckConstraint("octet_length(source_bytes) > 0", name="source_not_empty"),
        CheckConstraint("length(bill_id) > 0", name="bill_id_not_empty"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    bill_id: Mapped[str] = mapped_column(Text)
    tariff_id: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(Text)
    source_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    source_sha256: Mapped[str] = mapped_column(CHAR(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalculationRun(Base):
    """One calculation or reconciliation of a stored bill, with its exact report."""

    __tablename__ = "calculation_run"
    __table_args__ = (
        CheckConstraint("command IN ('calculate', 'reconcile')", name="command"),
        CheckConstraint("report_format = 'samay.report/1'", name="report_format"),
        CheckConstraint("tariff_status IN ('synthetic', 'verified')", name="tariff_status"),
        CheckConstraint(f"report_sha256 ~ {SHA256_HEX}", name="report_sha256"),
        # calculate always exits 0; reconcile exits 0 (clean) or 1 (differences).
        CheckConstraint(
            "(command = 'calculate' AND exit_code = 0)"
            " OR (command = 'reconcile' AND exit_code IN (0, 1))",
            name="exit_code",
        ),
        CheckConstraint(
            "explanation IS NULL OR explanation IN ('complete', 'partial', 'undeterminable')",
            name="explanation_value",
        ),
        # Only a reconciliation compares with the printed bill.
        CheckConstraint(
            "(command = 'calculate' AND explanation IS NULL AND printed_total_paise IS NULL"
            " AND total_difference_paise IS NULL)"
            " OR (command = 'reconcile' AND explanation IS NOT NULL)",
            name="reconcile_fields",
        ),
        # Difference = printed - calculated, known exactly when both totals are known.
        # (Every comparison is guarded with IS NOT NULL: a CHECK that evaluates to NULL passes.)
        CheckConstraint(
            "(printed_total_paise IS NOT NULL AND calculated_total_paise IS NOT NULL"
            " AND total_difference_paise IS NOT NULL"
            " AND total_difference_paise = printed_total_paise - calculated_total_paise)"
            " OR ((printed_total_paise IS NULL OR calculated_total_paise IS NULL)"
            " AND total_difference_paise IS NULL)",
            name="total_difference",
        ),
        Index(None, "bill_document_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    bill_document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bill_document.id", ondelete="RESTRICT")
    )
    command: Mapped[str] = mapped_column(Text)
    engine_version: Mapped[str] = mapped_column(Text)
    tariff_id: Mapped[str] = mapped_column(Text)
    tariff_name: Mapped[str] = mapped_column(Text)
    tariff_status: Mapped[str] = mapped_column(Text)
    exit_code: Mapped[int] = mapped_column(SmallInteger)
    report_format: Mapped[str] = mapped_column(Text)
    report_text: Mapped[str] = mapped_column(Text)
    report_sha256: Mapped[str] = mapped_column(CHAR(64))
    calculated_total_paise: Mapped[int | None] = mapped_column(BigInteger)
    printed_total_paise: Mapped[int | None] = mapped_column(BigInteger)
    total_difference_paise: Mapped[int | None] = mapped_column(BigInteger)
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
