"""Atomic file writes and tolerant YAML reading."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


class StorageError(RuntimeError):
    """A data file exists but cannot be read."""


def replace_path(source: Path, target: Path, attempts: int = 50, delay: float = 0.05) -> None:
    """``Path.replace`` that retries: on Windows virus scanners briefly lock freshly written files."""
    for attempt in range(attempts):
        try:
            Path(source).replace(target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to a temporary file next to ``path`` and move it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        replace_path(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_yaml(path: Path, data: Any) -> None:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    atomic_write_bytes(path, text.encode("utf-8"))


def read_yaml(path: Path) -> Any:
    """Content of a YAML file or ``None`` if it does not exist."""
    if not path.is_file():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as e:
        raise StorageError(f"{path} is not a valid UTF-8 YAML file: {e}") from e


def write_csv(path: Path, df: pd.DataFrame) -> None:
    atomic_write_bytes(path, df.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8"))


def read_csv(path: Path) -> pd.DataFrame:
    """All cells as strings; an empty file is an empty table."""
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except (UnicodeDecodeError, pd.errors.ParserError) as e:
        raise StorageError(f"{path} is not a valid UTF-8 CSV file: {e}") from e
