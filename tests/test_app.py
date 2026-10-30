import pytest

from mymoneyvisualizer.app import (
    ACCOUNTS,
    ALL_TOPICS,
    CATEGORIES,
    PROFILES,
    SETTINGS,
    TAGGERS,
    TRANSACTIONS,
    AppModel,
    Event,
    InvalidTaggerError,
)
from mymoneyvisualizer.domain.columns import ONE_TIME_TAGGER, Col
from mymoneyvisualizer.domain.models import Tagger
from mymoneyvisualizer.importing.profile import ImportProfile

from .helpers import transactions


@pytest.fixture
def model(tmp_path):
    return AppModel.open(tmp_path / "data")


@pytest.fixture
def events(model):
    received = []
    model.changed.connect(received.append)
    return received


@pytest.fixture
def filled(model):
    model.add_account("giro")
    model.add_account("spar")
    model.import_transactions(
        "giro",
        transactions(
            ("2024-01-02", "REWE", "Einkauf", -50.0),
            ("2024-01-03", "EDEKA", "Bio Einkauf", -20.0),
            ("2024-01-05", "Ich", "Sparen", -200.0),
            ("2024-01-31", "ACME", "Gehalt", 2000.0),
            ("2024-02-02", "Kiosk", "Zeitung", -2.0),
        ),
    )
    model.import_transactions("spar", transactions(("2024-01-05", "Ich", "Sparen Eingang", 200.0)))
    model.save_tagger(Tagger("groceries", tag="household.food", regex_recipient="REWE|EDEKA"))
    model.save_tagger(Tagger("salary", tag="income", regex_recipient="ACME"))
    model.save_tagger(Tagger("saving", tag="spar", regex_description="^Sparen$"))
    return model


def _reloaded(model):
    return AppModel.open(model.repository.data_dir)


def test_event():
    event, calls = Event(), []
    event.connect(calls.append)
    event.emit(1)
    event.disconnect(calls.append)
    event.emit(2)
    assert calls == [1]


def test_empty_model(model):
    assert model.account_names == []
    assert model.transactions().empty
    assert model.unique_tags() == []
    assert model.summary("2024-01", "2024-02") is None
    assert model.budget_report("basic") is None
    assert model.tagger_overview().empty


def test_reload_emits_all_topics(model, events):
    model.reload()
    assert events == [ALL_TOPICS]


def test_accounts_lifecycle(model, events):
    assert model.add_account() == "new account 1"
    assert model.add_account() == "new account 2"
    assert model.add_account("giro") == "giro"
    assert model.add_account("giro") == "giro_1"
    assert ACCOUNTS in events[0]
    assert model.rename_account("new account 1", "giro") == "giro_2"
    assert model.rename_account("giro_2", "  ") == "giro_2"
    model.delete_account("giro_1")
    assert model.account_names == ["giro_2", "new account 2", "giro"]  # renaming keeps the position
    assert _reloaded(model).account_names == ["giro_2", "new account 2", "giro"]


def test_rename_account_keeps_transfer_tags(filled):
    """Transfers are recognised by tags equal to an account name; renaming must not break that."""
    target = filled.account_transactions("giro").iloc[-1][Col.transaction_id]
    filled.set_one_time_tag(target, "spar")
    filled.rename_account("spar", "Tagesgeld")
    assert filled.tagger("saving").tag == "Tagesgeld"
    assert filled.one_time_tags[target].tag == "Tagesgeld"
    assert "Tagesgeld" not in set(filled.summary("2024-01", "2024-02")[Col.tag])
    assert _reloaded(filled).tagger("saving").tag == "Tagesgeld"


def test_import_and_tagging(filled):
    giro = filled.account_transactions("giro")
    assert list(giro[Col.date]) == sorted(giro[Col.date], reverse=True)
    assert dict(zip(giro[Col.recipient], giro[Col.tag], strict=True))["EDEKA"] == "household.food"
    assert filled.import_transactions("giro", transactions()) == 0
    assert filled.unique_base_tags() == ["", "household", "income", "spar"]
    assert len(_reloaded(filled).transactions()) == 6


def test_new_base_tags_get_a_category(filled, events):
    assert [(c.name, c.category) for c in filled.categories] == [
        ("", "basic"),
        ("household", "basic"),
        ("income", "basic"),
    ]
    filled.save_tagger(Tagger("kiosk", tag="hobby.news", regex_recipient="Kiosk"))
    assert CATEGORIES in events[-1]
    assert "hobby" in [c.name for c in filled.categories]


def test_save_tagger_validates_and_renames(filled, events):
    with pytest.raises(InvalidTaggerError) as error:
        filled.save_tagger(Tagger("bad", regex_recipient="(["))
    assert "regex_recipient" in error.value.errors

    clash = filled.save_tagger(Tagger("salary", tag="other"))
    assert clash.name == "salary_1"
    assert filled.save_tagger(Tagger(ONE_TIME_TAGGER)).name == f"{ONE_TIME_TAGGER}_1"
    assert filled.save_tagger(Tagger("  ")).name == "new_tagger"
    assert events[-1] == frozenset({TAGGERS, TRANSACTIONS})

    renamed = filled.save_tagger(Tagger("pay", tag="income.salary", regex_recipient="ACME"), original_name="salary")
    assert renamed.name == "pay"
    names = [t.name for t in filled.taggers]
    assert names.index("pay") == 1  # keeps its position = priority
    assert "salary" not in names
    assert _reloaded(filled).tagger("pay").tag == "income.salary"


def test_returned_objects_are_copies(filled):
    filled.tagger("salary").tag = "hacked"
    filled.taggers[0].tag = "hacked"
    filled.settings.excluded_tags.append("hacked")
    filled.categories[0].category = "income"
    assert filled.tagger("salary").tag == "income"
    assert filled.settings.excluded_tags == []
    assert filled.categories[0].category == "basic"


def test_delete_taggers(filled, events):
    count = len(events)
    filled.delete_taggers(["unknown"])
    assert len(events) == count
    filled.delete_taggers(["salary", "saving"])
    assert [t.name for t in filled.taggers] == ["groceries"]


def test_one_time_tags(filled):
    target = filled.account_transactions("giro").iloc[0][Col.transaction_id]
    filled.set_one_time_tag(target, "hobby", recurring=2)
    row = filled.transaction(target)
    assert (row[Col.tag], row[Col.tagger_name], row[Col.recurring]) == ("hobby", ONE_TIME_TAGGER, 2.0)
    assert _reloaded(filled).transaction(target)[Col.tag] == "hobby"
    filled.remove_one_time_tag(target)
    filled.remove_one_time_tag(target)
    assert filled.transaction(target)[Col.tagger_name] == ""
    assert filled.transaction("unknown") is None


def test_delete_account_removes_its_one_time_tags(filled):
    target = filled.account_transactions("spar").iloc[0][Col.transaction_id]
    filled.set_one_time_tag(target, "x")
    filled.delete_account("spar")
    assert filled.one_time_tags == {}


def test_preview_tagger(filled):
    kiosk = filled.account_transactions("giro").iloc[0][Col.transaction_id]
    preview = filled.preview_tagger(Tagger("draft", tag="shop", regex_description="Einkauf"), transaction_id=kiosk)
    assert list(preview[Col.recipient]) == ["Kiosk", "EDEKA", "REWE"]
    assert list(preview[Col.tag]) == ["", "shop", "shop"]
    # nothing was saved
    assert filled.tagger("draft") is None


def test_preview_of_edited_tagger_ignores_saved_version(filled):
    edited = Tagger("groceries", tag="food", regex_recipient="EDEKA")
    preview = filled.preview_tagger(edited, original_name="groceries")
    assert list(preview[Col.recipient]) == ["EDEKA"]
    assert filled.preview_tagger(Tagger("x", regex_recipient="([")).empty


def test_preview_does_not_override_one_time_tags(filled):
    target = filled.account_transactions("giro").iloc[-1][Col.transaction_id]  # REWE
    filled.set_one_time_tag(target, "gift")
    preview = filled.preview_tagger(Tagger("draft", tag="shop", regex_recipient="REWE"))
    assert preview.empty


def test_save_profile(model, events):
    first = model.save_profile(ImportProfile(col_date="d"))
    assert first.name == "importer_1"
    second = model.save_profile(ImportProfile(name="dkb"))
    assert [p.name for p in model.profiles] == ["dkb", "importer_1"]
    model.save_profile(first, original_name=first.name)
    assert [p.name for p in model.profiles] == ["importer_1", "dkb"]  # most recently used first
    clash = model.save_profile(ImportProfile(name="dkb", skiprows=3), original_name=None)
    assert clash.name == "dkb_1"
    model.save_profile(ImportProfile(name="dkb", skiprows=5), original_name="dkb")
    assert next(p for p in model.profiles if p.name == "dkb").skiprows == 5
    assert events[-1] == frozenset({PROFILES})
    assert second.name == "dkb"


def test_settings(model, events):
    model.update_settings(excluded_tags=["x"])
    assert events[-1] == frozenset({SETTINGS})
    count = len(events)
    model.update_settings(excluded_tags=["x"])
    assert len(events) == count
    model.set_budget_period(2025, 2023)
    model.set_budget_factor("basic", 0.45)
    settings = _reloaded(model).settings
    assert (settings.budget_start, settings.budget_end) == (2023, 2025)
    assert settings.budget_factors["basic"] == 0.45


def test_assign_categories(filled):
    filled.assign_categories({"income": ["income"], "basic": ["household"], "optional": [""]})
    assert [(c.name, c.category) for c in _reloaded(filled).categories] == [
        ("income", "income"),
        ("household", "basic"),
        ("", "optional"),
    ]


def test_summary_respects_settings(filled):
    table = filled.summary("2024-01", "2024-02").set_index(Col.tag)
    assert "spar" not in table.index  # transfers hidden by default
    filled.update_settings(hide_transfers=False, excluded_tags=["income"])
    table = filled.summary("2024-01", "2024-02").set_index(Col.tag)
    assert "spar" in table.index
    assert "income" not in table.index
    deviation, _ = filled.summary_deviations("2024-01", "2024-02")
    assert list(deviation.columns) == ["2024-01", "2024-02"]


def test_detail(filled):
    detail = filled.detail("2024-01", "household")
    assert list(detail[Col.recipient]) == ["REWE", "EDEKA"]
    assert set(detail[Col.account]) == {"giro"}
    total = filled.detail("2024-01", None)
    assert list(total[Col.description]) == ["Einkauf", "Bio Einkauf", "Sparen Eingang", "Gehalt"]  # "Sparen" hidden


def test_budget_and_overview(filled):
    filled.assign_categories({"income": ["income"]})
    filled.set_budget_period(2024, 2024)
    series = filled.budget_series()
    assert "spar" not in series.monthly.columns
    report = filled.budget_report("basic", series)
    assert report.consumed[0][0] == "household"
    assert filled.budget_report("optional").consumed == []
    overview = filled.tagger_overview().set_index("name")
    assert overview.loc["groceries", "count"] == 2


def test_backup_restore_reloads_state(filled, tmp_path, events):
    filled.create_backup(tmp_path / "b.zip")
    filled.delete_account("giro")
    previous = filled.restore_backup(tmp_path / "b.zip")
    assert previous is not None
    assert filled.account_names == ["giro", "spar"]
    assert events[-1] == ALL_TOPICS
