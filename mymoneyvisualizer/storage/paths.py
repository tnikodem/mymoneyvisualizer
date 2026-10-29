"""Where the data directory lives."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import platformdirs

APP_NAME = "MyMoneyVisualizer"
ENV_VAR = "MMV_DATA_DIR"


def default_data_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def resolve_data_dir(argument: str | None = None, environ: Mapping[str, str] | None = None) -> Path:
    """Data directory from ``--data-dir``, ``$MMV_DATA_DIR`` or the user data dir."""
    environ = os.environ if environ is None else environ
    if argument:
        return Path(argument).expanduser()
    if environ.get(ENV_VAR):
        return Path(environ[ENV_VAR]).expanduser()
    return default_data_dir()
