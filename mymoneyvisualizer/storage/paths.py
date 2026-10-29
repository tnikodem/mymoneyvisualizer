"""Where the data directory lives."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

import platformdirs

logger = logging.getLogger(__name__)

APP_NAME = "MyMoneyVisualizer"
ENV_VAR = "MMV_DATA_DIR"
LEGACY_DIR_NAME = "config"
LEGACY_MARKERS = ("accounts.yaml", "taggers.yaml", "importers.yaml")


def default_data_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def resolve_data_dir(
    argument: str | None = None, environ: Mapping[str, str] | None = None, cwd: Path | None = None
) -> Path:
    """Data directory from ``--data-dir``, ``$MMV_DATA_DIR``, a legacy ``./config`` or the user data dir.

    Version 0.1 always used ``./config`` relative to the working directory, so an existing one is kept
    to not lose access to the data.
    """
    environ = os.environ if environ is None else environ
    if argument:
        return Path(argument).expanduser()
    if environ.get(ENV_VAR):
        return Path(environ[ENV_VAR]).expanduser()
    legacy = (cwd or Path.cwd()) / LEGACY_DIR_NAME
    if any((legacy / marker).is_file() for marker in LEGACY_MARKERS):
        logger.warning("using legacy data directory %s, consider moving it to %s", legacy, default_data_dir())
        return legacy
    return default_data_dir()
