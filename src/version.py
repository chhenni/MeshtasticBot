"""Version information for MeshtasticBot.

Priority order:
1. APP_VERSION env var — set as a Docker build arg by CI (GitVersion semver).
2. pyproject.toml — fallback for local / development runs.

An optional GIT_COMMIT env var (first 7 chars) is appended when present,
e.g. "v1.2.3 (abc1234)".
"""

import os
import tomllib
from pathlib import Path

_env_version: str = os.environ.get("APP_VERSION", "")
if _env_version:
    __version__: str = _env_version
else:
    _PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"
    with _PYPROJECT.open("rb") as _f:
        __version__ = tomllib.load(_f)["project"]["version"]

_git_commit: str = os.environ.get("GIT_COMMIT", "")

VERSION_STRING: str = f"v{__version__}" + (f" ({_git_commit[:7]})" if _git_commit else "")
