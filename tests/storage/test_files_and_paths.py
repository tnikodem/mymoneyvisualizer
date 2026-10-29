from pathlib import Path

import pandas as pd
import pytest

from mymoneyvisualizer.storage import files
from mymoneyvisualizer.storage.files import StorageError, atomic_write_bytes, read_csv, read_yaml, write_csv, write_yaml
from mymoneyvisualizer.storage.paths import ENV_VAR, default_data_dir, resolve_data_dir


def test_yaml_roundtrip_keeps_unicode(tmp_path):
    path = tmp_path / "sub" / "x.yaml"
    write_yaml(path, [{"tag": "küche", "recurring": None}])
    assert "küche" in path.read_text(encoding="utf-8")
    assert read_yaml(path) == [{"tag": "küche", "recurring": None}]


def test_read_yaml_missing_and_cp1252(tmp_path):
    assert read_yaml(tmp_path / "missing.yaml") is None
    path = tmp_path / "old.yaml"
    path.write_bytes("- tag: küche\n".encode("cp1252"))
    assert read_yaml(path) == [{"tag": "küche"}]


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


def test_csv_roundtrip_and_encodings(tmp_path):
    path = tmp_path / "a.csv"
    write_csv(path, pd.DataFrame({"date": pd.to_datetime(["2024-01-02"]), "recipient": ["Müller"]}))
    assert path.read_text(encoding="utf-8").splitlines() == ["date,recipient", "2024-01-02,Müller"]
    assert read_csv(path).to_dict("records") == [{"date": "2024-01-02", "recipient": "Müller"}]

    old = tmp_path / "old.csv"
    old.write_bytes("recipient\nMüller\n".encode("cp1252"))
    assert read_csv(old)["recipient"].iloc[0] == "Müller"

    empty = tmp_path / "empty.csv"
    empty.write_text("")
    assert read_csv(empty).empty


def test_read_csv_invalid(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text('a,b\n"unterminated,2\n1,2,3,4\n')
    with pytest.raises(StorageError):
        read_csv(path)


def test_resolve_data_dir_priorities(tmp_path):
    assert resolve_data_dir("~/x", environ={}, cwd=tmp_path) == Path("~/x").expanduser()
    assert resolve_data_dir(str(tmp_path / "arg"), environ={ENV_VAR: "env"}, cwd=tmp_path) == tmp_path / "arg"
    assert resolve_data_dir(None, environ={ENV_VAR: str(tmp_path / "env")}, cwd=tmp_path) == tmp_path / "env"
    assert resolve_data_dir(None, environ={}, cwd=tmp_path) == default_data_dir()


def test_resolve_data_dir_keeps_legacy_config(tmp_path, caplog):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "taggers.yaml").write_text("[]")
    assert resolve_data_dir(None, environ={}, cwd=tmp_path) == tmp_path / "config"
    assert "legacy" in caplog.text


def test_resolve_data_dir_uses_process_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "from-env"))
    assert resolve_data_dir() == tmp_path / "from-env"
