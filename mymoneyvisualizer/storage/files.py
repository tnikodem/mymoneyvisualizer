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
    """Content of a YAML file or ``None`` if it does not exist.

    Version 0.1 wrote YAML in the platform encoding (cp1252 on Windows), so that is accepted as well.
    """
    if not path.is_file():
        return None
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise StorageError(f"{path} is not valid YAML: {e}") from e


def write_csv(path: Path, df: pd.DataFrame) -> None:
    atomic_write_bytes(path, df.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8"))


def read_csv(path: Path) -> pd.DataFrame:
    """All cells as strings; an empty file is an empty table."""
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, keep_default_na=False, encoding=encoding)
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
        except pd.errors.ParserError as e:
            raise StorageError(f"{path} is not a valid CSV file: {e}") from e
    raise StorageError(f"cannot decode {path}")  # pragma: no cover - latin-1 decodes every byte
