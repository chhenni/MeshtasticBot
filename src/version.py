"""Version information for MeshtasticBot.

The version is read from pyproject.toml at import time.
An optional GIT_COMMIT environment variable (e.g. set during Docker builds)
is appended to provide traceability back to the exact build.
"""

import os
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"

with _PYPROJECT.open("rb") as _f:
    __version__: str = tomllib.load(_f)["project"]["version"]

_git_commit: str = os.environ.get("GIT_COMMIT", "")

VERSION_STRING: str = f"v{__version__}" + (f" ({_git_commit[:7]})" if _git_commit else "")
