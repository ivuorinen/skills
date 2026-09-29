"""Load a module from a file path, for scripts `import` cannot reach.

A hyphenated filename (`check-rules-anatomy.py`) is not a valid identifier, and a
shipped tool is loaded by path so a test gets its own copy. Every test file used
to repeat the three-line `spec_from_file_location` load with two pyright
suppressions over the Optional it never checked, so a moved script failed as
`'NoneType' object has no attribute 'loader'` instead of naming the path
(audit-b7943908). This is the one checked copy.

A helper module rather than conftest.py: pytest loads conftest itself and
advises against importing from it.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_path(name: str, path: Path) -> ModuleType:
    """Execute `path` as module `name` and return it.

    The module is registered in `sys.modules` before it runs: a dataclass
    resolves its annotations through `sys.modules[cls.__module__]`, and an
    unregistered module makes that lookup fail at class creation. The entry is
    left in place, so a later load under the same name replaces it.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name!r}: no module loader for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
