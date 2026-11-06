"""SAMAY's own database: saved bills and their calculation reports (Step 4).

This package stores what the calculation engine produced; it never calculates,
adjusts or reinterprets money. The engine packages (core, tariffs, billing, io)
never import it (a test enforces this).
"""

from .config import DatabaseConfigError, database_url
from .models import Base, BillDocument, CalculationRun
from .store import (
    COMMANDS,
    ENGINE_VERSION,
    OUTCOME_TEXT,
    RunNotFoundError,
    RunSummary,
    SavedRun,
    StoredRun,
    VerifyResult,
    get_run,
    list_runs,
    save_bill,
    verify_run,
)

__all__ = [
    "COMMANDS",
    "ENGINE_VERSION",
    "OUTCOME_TEXT",
    "Base",
    "BillDocument",
    "CalculationRun",
    "DatabaseConfigError",
    "RunNotFoundError",
    "RunSummary",
    "SavedRun",
    "StoredRun",
    "VerifyResult",
    "database_url",
    "get_run",
    "list_runs",
    "save_bill",
    "verify_run",
]
