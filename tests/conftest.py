import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def _clean_degraded_record():
    """Start every test with an empty `pr_common` degraded record.

    `best_effort` records a failed secondary fetch in a module-level list that
    only an envelope drains, so a test that fails a fetch without building one
    would leave its failure for the next test's envelope to report. Tests load
    `pr_common` both by import and by path, so every loaded copy is cleared.
    """
    for module in list(sys.modules.values()):
        record = getattr(module, "_DEGRADED", None)
        if isinstance(record, list) and hasattr(module, "best_effort"):
            record.clear()
    yield
