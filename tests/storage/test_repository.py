import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml

from mymoneyvisualizer.domain.columns import RAW_COLUMNS, Col
from mymoneyvisualizer.domain.models import OneTimeTag, Settings, TagCategory, Tagger
from mymoneyvisualizer.importing.profile import ImportProfile
from mymoneyvisualizer.storage.files import StorageError
from mymoneyvisualizer.storage.repository import Repository, State, account_file_name

from ..helpers import transactions

LEGACY = Path(__file__).parents[1] / "data" / "legacy_v0_1"
KIOSK_ID = "baf50524-fc60-42a8-a24d-e1d6e7f92e4d"


@pytest.fixture
def legacy_dir(tmp_path, monkeypatch):
    """The data directory written by version 0.1, used from the directory the app was started in."""
    shutil.copytree(LEGACY / "config", tmp_path / "config")
    monkeypatch.chdir(tmp_path)
    return tmp_path / "config"


def _yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_account_file_name():
    assert account_file_name("Giro Konto") == "accounts/Giro_Konto.csv"
    assert account_file_name('a/b:c*"d') == "accounts/a_b_c_d.csv"
    assert account_file_name("...") == "accounts/account.csv"
    assert account_file_name("x", ["accounts/X.csv", "accounts/x_2.csv"]) == "accounts/x_3.csv"


def test_empty_directory(tmp_path):
    state = Repository(tmp_path / "nothing").load()
    assert state == State(settings=state.settings)
    assert not (tmp_path / "nothing").exists()


def test_roundtrip(tmp_path):
    repo = Repository(tmp_path)
    state = State(
        accounts={"Giro Konto": transactions(("2024-01-02", "Müller", "Brot", -3.5)), "empty": transactions()},
        taggers=[Tagger("t", tag="küche", regex_recipient="Müller", recurring=2)],
        one_time_tags={"id": OneTimeTag("id", "hobby", None)},
        categories=[TagCategory("küche", "optional"), TagCategory("", "basic")],
        profiles=[ImportProfile(name="dkb", skiprows=4)],
        settings=Settings(excluded_tags=["x"], budget_start=2020, budget_end=2021),
    )
    repo.save_all(state)
    loaded = Repository(tmp_path).load()
    pd.testing.assert_frame_equal(loaded.accounts["Giro Konto"], state.accounts["Giro Konto"])
    assert loaded.accounts["empty"].empty
    assert (loaded.taggers, loaded.one_time_tags, loaded.categories, loaded.profiles, loaded.settings) == (
        state.taggers,
        state.one_time_tags,
        state.categories,
        state.profiles,
        state.settings,
    )
    assert _yaml(tmp_path / "accounts.yaml") == [
        {"name": "Giro Konto", "file": "accounts/Giro_Konto.csv"},
        {"name": "empty", "file": "accounts/empty.csv"},
    ]


def test_account_csv_contains_only_raw_columns(tmp_path):
    repo = Repository(tmp_path)
    df = transactions(("2024-01-02", "a", "b", -1.0)).assign(tag="derived")
    repo.save_account("x", df)
    assert (tmp_path / "accounts" / "x.csv").read_text().splitlines()[0] == ",".join(RAW_COLUMNS)


def test_rename_and_delete_account_files(tmp_path):
    repo = Repository(tmp_path)
    repo.save_account("old name", transactions(("2024-01-02", "a", "b", -1.0)))
    repo.rename_account("old name", "new name")
    repo.save_account_index(["new name"])
    assert not (tmp_path / "accounts" / "old_name.csv").exists()
    assert repo.account_file("new name") == tmp_path / "accounts" / "new_name.csv"
    assert len(Repository(tmp_path).load().accounts["new name"]) == 1
    repo.delete_account("new name")
    assert not (tmp_path / "accounts" / "new_name.csv").exists()
    repo.delete_account("unknown")


def test_invalid_files_raise_instead_of_losing_data(tmp_path):
    (tmp_path / "taggers.yaml").write_text("name: not a list\n")
    with pytest.raises(StorageError, match="taggers.yaml"):
        Repository(tmp_path).load()


def test_migrates_version_0_1(legacy_dir):
    state = Repository(legacy_dir).load()

    assert list(state.accounts) == ["Giro Konto", "spar"]
    giro = state.accounts["Giro Konto"]
    assert list(giro.columns) == list(RAW_COLUMNS)
    assert set(giro[Col.recipient]) == {"ACME GmbH", "Ich", "Kiosk", "Bäckerei Müller"}
    # the one-time tag lived in the account csv
    assert state.one_time_tags == {KIOSK_ID: OneTimeTag(KIOSK_ID, "hobby", None)}
    assert [t.tag for t in state.taggers] == ["küche.brot", "income", "spar"]
    assert state.profiles[0].separator == ";"
    assert state.profiles[0].col_value == "Betrag (€)"
    assert [c.name for c in state.categories] == ["", "income", "küche"]
    assert (state.settings.budget_start, state.settings.budget_end) == (2023, 2024)
    assert state.settings.budget_factors["optional"] == 0.4
    assert state.settings.excluded_tags == ["spar"]

    # files were rewritten in the new layout
    assert _yaml(legacy_dir / "accounts.yaml")[0] == {"name": "Giro Konto", "file": "accounts/Giro_Konto.csv"}
    header = (legacy_dir / "accounts" / "Giro_Konto.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(RAW_COLUMNS)
    assert _yaml(legacy_dir / "one_time_tags.yaml") == [{"transaction_id": KIOSK_ID, "tag": "hobby", "recurring": None}]

    # loading again gives the same state
    again = Repository(legacy_dir).load()
    pd.testing.assert_frame_equal(again.accounts["Giro Konto"], giro)
    assert again.one_time_tags == state.one_time_tags


def test_migrates_account_without_ids_and_with_recurring_column(tmp_path):
    (tmp_path / "accounts").mkdir()
    (tmp_path / "accounts.yaml").write_text("- name: a\n  db_filepath: /somewhere/else/a.csv\n")
    (tmp_path / "accounts" / "a.csv").write_text(
        "date,recipient,description,value,recurring,tag,tagger_name\n2024-01-02,x,,-1.0,2.0, ,\n"
    )
    state = Repository(tmp_path).load()
    df = state.accounts["a"]
    assert len(df[Col.transaction_id].iloc[0]) == 36
    assert df[Col.description].iloc[0] == ""
    # the generated id is stored, so one-time tags keep working after a restart
    assert Repository(tmp_path).load().accounts["a"][Col.transaction_id].iloc[0] == df[Col.transaction_id].iloc[0]


def test_missing_account_file_gives_empty_account(tmp_path):
    (tmp_path / "accounts.yaml").write_text("- name: a\n  db_filepath: ./gone/a.csv\n- name: a\n- name: ''\n")
    state = Repository(tmp_path).load()
    assert list(state.accounts) == ["a"]
    assert state.accounts["a"].empty


def test_duplicate_categories_keep_first(tmp_path):
    (tmp_path / "tag_categories.yaml").write_text("- {name: food, category: basic}\n- {name: food, category: income}\n")
    assert Repository(tmp_path).load().categories == [TagCategory("food", "basic")]
