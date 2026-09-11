"""Schema definitions mentioning the same table and columns."""

LEDGER = """
CREATE TABLE ledger (
  account TEXT NOT NULL,
  period  TEXT NOT NULL,
  cents   INTEGER NOT NULL
)
"""
