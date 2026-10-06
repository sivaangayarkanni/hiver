"""Vercel entrypoint (zero-config FastAPI detects ``app/main.py``).

Re-exports the web app. ``src/`` is added to ``sys.path`` so the package
imports even when the project itself isn't pip-installed in the function
environment (Vercel installs the dependencies, not the project).
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hiver_agent.web.app import app  # noqa: E402

__all__ = ["app"]
