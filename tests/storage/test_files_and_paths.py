from pathlib import Path

import pandas as pd
import pytest

from mymoneyvisualizer.storage import files
from mymoneyvisualizer.storage.files import StorageError, atomic_write_bytes, read_csv, read_yaml, write_csv, write_yaml
from mymoneyvisualizer.storage.paths import ENV_VAR, default_data_dir, resolve_data_dir


def test_yaml_roundtrip_keeps_unicode(tmp_path):
    path = tmp_path / "sub" / "x.yaml"
    write_yaml(path, [{"category": "küche", "sale_of": None}])
    assert "küche" in path.read_text(encoding="utf-8")
    assert read_yaml(path) == [{"category": "küche", "sale_of": None}]


def test_read_yaml_missing_and_not_utf8(tmp_path):
    assert read_yaml(tmp_path / "missing.yaml") is None
    path = tmp_path / "latin.yaml"
    path.write_bytes("- category: küche\n".encode("latin-1"))
    with pytest.raises(StorageError, match="UTF-8"):
        read_yaml(path)


def test_read_yaml_invalid(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("a: [unclosed\n")
    with pytest.raises(StorageError, match="broken.yaml"):
        read_yaml(path)


def test_atomic_write_leaves_old_file_on_error(tmp_path, monkeypatch):
    path = tmp_path / "data.txt"
    path.write_text("old")

    def fail(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(files.Path, "replace", fail)
    with pytest.raises(OSError):
        atomic_write_bytes(path, b"new")
    assert path.read_text() == "old"
    assert list(tmp_path.iterdir()) == [path]


def test_replace_retries_while_file_is_locked(tmp_path, monkeypatch):
    """Windows virus scanners lock freshly written files for a moment."""
    real_replace, calls = files.Path.replace, []

    def flaky(self, target):
        calls.append(self)
        if len(calls) < 3:
            raise PermissionError("locked")
        return real_replace(self, target)

    monkeypatch.setattr(files.Path, "replace", flaky)
    path = tmp_path / "x.yaml"
    write_yaml(path, {"a": 1})
    assert len(calls) == 3
    assert read_yaml(path) == {"a": 1}


def test_replace_gives_up_eventually(tmp_path, monkeypatch):
    def locked(self, target):
        raise PermissionError("locked")

    monkeypatch.setattr(files.Path, "replace", locked)
    with pytest.raises(PermissionError):
        files.replace_path(tmp_path / "a", tmp_path / "b", attempts=3, delay=0)


def test_csv_roundtrip(tmp_path):
    path = tmp_path / "a.csv"
    write_csv(path, pd.DataFrame({"date": pd.to_datetime(["2024-01-02"]), "recipient": ["Müller"]}))
    assert path.read_text(encoding="utf-8").splitlines() == ["date,recipient", "2024-01-02,Müller"]
    assert read_csv(path).to_dict("records") == [{"date": "2024-01-02", "recipient": "Müller"}]

    empty = tmp_path / "empty.csv"
    empty.write_text("")
    assert read_csv(empty).empty


def test_read_csv_invalid(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text('a,b\n"unterminated,2\n1,2,3,4\n')
    with pytest.raises(StorageError):
        read_csv(path)


def test_resolve_data_dir_priorities(tmp_path):
    assert resolve_data_dir("~/x", environ={}) == Path("~/x").expanduser()
    assert resolve_data_dir(str(tmp_path / "arg"), environ={ENV_VAR: "env"}) == tmp_path / "arg"
    assert resolve_data_dir(None, environ={ENV_VAR: str(tmp_path / "env")}) == tmp_path / "env"
    assert resolve_data_dir(None, environ={}) == default_data_dir()


def test_resolve_data_dir_uses_process_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "from-env"))
    assert resolve_data_dir() == tmp_path / "from-env"
