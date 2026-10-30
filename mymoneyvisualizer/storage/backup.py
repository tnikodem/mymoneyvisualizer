"""Backups of the data directory as zip files ("Save Project" / "Load Project")."""

from __future__ import annotations

import datetime
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from mymoneyvisualizer.storage.files import StorageError, replace_path
from mymoneyvisualizer.storage.repository import ACCOUNTS_DIR, ACCOUNTS_FILE, DATA_FILES, RULES_FILE, Repository


def _is_data_member(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return False
    if len(path.parts) == 1:
        return path.name in DATA_FILES
    return len(path.parts) == 2 and path.parts[0] == ACCOUNTS_DIR and path.suffix == ".csv"


def create_backup(data_dir: str | Path, zip_path: str | Path) -> list[str]:
    """Zip all data files; returns the archive members."""
    data_dir = Path(data_dir)
    members = [name for name in DATA_FILES if (data_dir / name).is_file()]
    accounts = data_dir / ACCOUNTS_DIR
    if accounts.is_dir():
        members += [f"{ACCOUNTS_DIR}/{p.name}" for p in sorted(accounts.glob("*.csv"))]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for member in members:
            archive.write(data_dir / member, arcname=member)
    return members


def restore_backup(zip_path: str | Path, data_dir: str | Path) -> Path | None:
    """Replace the data directory by the content of a backup.

    The archive is extracted and loaded in a staging directory first, so a broken backup never touches
    the current data. The previous data directory is kept next to it; its path is returned.
    """
    zip_path, data_dir = Path(zip_path), Path(data_dir)
    if not zipfile.is_zipfile(zip_path):
        raise StorageError(f"{zip_path} is not a zip file")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    staging = data_dir.with_name(f".{data_dir.name}.restore-{stamp}")
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = [m for m in archive.namelist() if _is_data_member(m)]
            if not {ACCOUNTS_FILE, RULES_FILE} & set(members):
                raise StorageError(f"{zip_path} is not a MyMoneyVisualizer backup")
            if archive.testzip() is not None:
                raise StorageError(f"{zip_path} is corrupt")
            for member in members:
                target = staging / member.replace("\\", "/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
        Repository(staging).load()  # fails on broken files before the current data is touched
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    previous = None
    if data_dir.exists():
        previous = data_dir.with_name(f"{data_dir.name}.before-restore-{stamp}")
        replace_path(data_dir, previous)
    replace_path(staging, data_dir)
    return previous
