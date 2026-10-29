import shutil
import zipfile
from pathlib import Path

import pytest

from mymoneyvisualizer.domain.models import TagCategory, Tagger
from mymoneyvisualizer.storage.backup import create_backup, restore_backup
from mymoneyvisualizer.storage.files import StorageError
from mymoneyvisualizer.storage.repository import Repository, State

from ..helpers import transactions

LEGACY = Path(__file__).parents[1] / "data" / "legacy_v0_1"


def _state():
    return State(
        accounts={"giro": transactions(("2024-01-02", "a", "b", -1.0))},
        taggers=[Tagger("t", tag="x")],
        categories=[TagCategory("x", "optional")],
    )


def test_backup_and_restore_roundtrip(tmp_path):
    data = tmp_path / "data"
    Repository(data).save_all(_state())
    members = create_backup(data, tmp_path / "backup.zip")
    assert "tag_categories.yaml" in members
    assert "accounts/giro.csv" in members

    Repository(data).save_all(State(accounts={"other": transactions()}))
    previous = restore_backup(tmp_path / "backup.zip", data)

    restored = Repository(data).load()
    assert list(restored.accounts) == ["giro"]
    assert restored.categories == [TagCategory("x", "optional")]  # regression: categories were never restored
    assert previous is not None and (previous / "accounts" / "other.csv").is_file()


def test_restore_into_missing_directory(tmp_path):
    source = tmp_path / "source"
    Repository(source).save_all(_state())
    create_backup(source, tmp_path / "b.zip")
    assert restore_backup(tmp_path / "b.zip", tmp_path / "new") is None
    assert list(Repository(tmp_path / "new").load().accounts) == ["giro"]


def test_restore_backup_of_version_0_1(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no ./config here, the files must come from the zip
    restore_backup(LEGACY / "mmv_backup.zip", tmp_path / "data")
    state = Repository(tmp_path / "data").load()
    assert list(state.accounts) == ["Giro Konto", "spar"]
    assert len(state.accounts["Giro Konto"]) == 4
    assert len(state.one_time_tags) == 1


def test_restore_old_backup_ignores_live_config_of_working_directory(tmp_path, monkeypatch):
    live = tmp_path / "config"
    shutil.copytree(LEGACY / "config", live)
    (live / "accounts" / "Giro_Konto.csv").write_text("transaction_id,date,recipient,description,value\n")
    monkeypatch.chdir(tmp_path)
    restore_backup(LEGACY / "mmv_backup.zip", tmp_path / "data")
    assert len(Repository(tmp_path / "data").load().accounts["Giro Konto"]) == 4


@pytest.mark.parametrize("kind", ["not-a-zip", "foreign-zip", "broken-content"])
def test_invalid_backup_leaves_data_untouched(tmp_path, kind):
    data = tmp_path / "data"
    Repository(data).save_all(_state())
    before = sorted(p.relative_to(data) for p in data.rglob("*"))
    archive = tmp_path / "backup.zip"
    if kind == "not-a-zip":
        archive.write_text("hello")
    else:
        with zipfile.ZipFile(archive, "w") as z:
            if kind == "foreign-zip":
                z.writestr("readme.txt", "x")
            else:
                z.writestr("taggers.yaml", "name: [unclosed")
    with pytest.raises(StorageError):
        restore_backup(archive, data)
    assert sorted(p.relative_to(data) for p in data.rglob("*")) == before
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


def test_restore_ignores_unsafe_members(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("taggers.yaml", "[]")
        z.writestr("../escape.yaml", "x")
        z.writestr("/abs.yaml", "x")
        z.writestr("accounts/../../x.csv", "x")
        z.writestr("accounts/nested/y.csv", "x")
        z.writestr("other.txt", "x")
    restore_backup(archive, tmp_path / "data")
    assert sorted(p.name for p in (tmp_path / "data").rglob("*")) == ["taggers.yaml"]
    assert not (tmp_path / "escape.yaml").exists()
