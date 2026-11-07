"""SAMAY's HTTP API (Step 5): a thin layer over samay.db and the bill engine.

It never calculates money. Bills are checked, calculated and reconciled by the
same engine path as the command line (via samay.db.save_bill), and saved
reports are returned exactly as they were stored.
"""

from .app import create_app

__all__ = ["create_app"]
