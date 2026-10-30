import pandas as pd
import pytest
import yaml

from mymoneyvisualizer.domain.columns import RAW_COLUMNS
from mymoneyvisualizer.domain.models import GroupAssignment, ManualCategory, Rule, Settings
from mymoneyvisualizer.importing.profile import ImportProfile
from mymoneyvisualizer.storage.files import StorageError
from mymoneyvisualizer.storage.repository import Repository, State, account_file_name

from ..helpers import transactions


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
        rules=[Rule("t", category="küche", regex_recipient="Müller", recurring=2)],
        manual_categories={"id": ManualCategory("id", "hobby", None)},
        groups=[GroupAssignment("küche", "wants"), GroupAssignment("", "needs")],
        profiles=[ImportProfile(name="dkb", skiprows=4)],
        settings=Settings(excluded_categories=["x"], budget_start=2020, budget_end=2021),
    )
    repo.save_all(state)
    loaded = Repository(tmp_path).load()
    pd.testing.assert_frame_equal(loaded.accounts["Giro Konto"], state.accounts["Giro Konto"])
    assert loaded.accounts["empty"].empty
    assert (loaded.rules, loaded.manual_categories, loaded.groups, loaded.profiles, loaded.settings) == (
        state.rules,
        state.manual_categories,
        state.groups,
        state.profiles,
        state.settings,
    )
    assert _yaml(tmp_path / "accounts.yaml") == [
        {"name": "Giro Konto", "file": "accounts/Giro_Konto.csv"},
        {"name": "empty", "file": "accounts/empty.csv"},
    ]


def test_account_csv_contains_only_raw_columns(tmp_path):
    repo = Repository(tmp_path)
    df = transactions(("2024-01-02", "a", "b", -1.0)).assign(category="derived")
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
    (tmp_path / "rules.yaml").write_text("name: not a list\n")
    with pytest.raises(StorageError, match="rules.yaml"):
        Repository(tmp_path).load()


def test_missing_account_file_gives_empty_account(tmp_path):
    (tmp_path / "accounts.yaml").write_text("- name: a\n  file: accounts/gone.csv\n")
    state = Repository(tmp_path).load()
    assert list(state.accounts) == ["a"]
    assert state.accounts["a"].empty


@pytest.mark.parametrize("entry", ["- name: a\n", "- file: accounts/a.csv\n", "- name: ''\n  file: x.csv\n"])
def test_incomplete_account_entry_is_an_error(tmp_path, entry):
    (tmp_path / "accounts.yaml").write_text(entry)
    with pytest.raises(StorageError, match="accounts.yaml"):
        Repository(tmp_path).load()


def test_account_csv_must_be_utf8(tmp_path):
    (tmp_path / "accounts").mkdir()
    (tmp_path / "accounts.yaml").write_text("- name: a\n  file: accounts/a.csv\n")
    (tmp_path / "accounts" / "a.csv").write_bytes("recipient\nMüller\n".encode("latin-1"))
    with pytest.raises(StorageError, match="UTF-8"):
        Repository(tmp_path).load()


def test_duplicate_group_assignments_keep_first(tmp_path):
    content = "- {category: food, group: needs}\n- {category: food, group: income}\n"
    (tmp_path / "budget_groups.yaml").write_text(content)
    assert Repository(tmp_path).load().groups == [GroupAssignment("food", "needs")]
