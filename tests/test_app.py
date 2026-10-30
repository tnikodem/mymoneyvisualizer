import pytest

from mymoneyvisualizer.app import (
    ACCOUNTS,
    ALL_TOPICS,
    GROUPS,
    PROFILES,
    RULES,
    SETTINGS,
    TRANSACTIONS,
    AppModel,
    Event,
    InvalidRuleError,
)
from mymoneyvisualizer.domain.columns import MANUAL_RULE, Col
from mymoneyvisualizer.domain.models import ManualCategory, Rule
from mymoneyvisualizer.importing.profile import ImportProfile

from .helpers import rule_of, transactions


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
    model.save_rule(Rule(category="household.food", regex_recipient="REWE|EDEKA"))
    model.save_rule(Rule(category="income", regex_recipient="ACME"))
    model.save_rule(Rule(category="spar", regex_description="^Sparen$"))
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
    assert model.unique_categories() == []
    assert model.income_expenses("2024-01", "2024-02") is None
    assert model.budget_report() is None
    assert model.rule_overview().empty


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


def test_rename_account_keeps_transfer_categories(filled):
    """Transfers are recognised by categories equal to an account name; renaming must not break that."""
    target = filled.account_transactions("giro").iloc[-1][Col.transaction_id]
    filled.save_manual_category(ManualCategory(target, "spar"))
    filled.rename_account("spar", "Tagesgeld")
    assert [r.category for r in filled.rules] == ["household.food", "income", "Tagesgeld"]
    assert filled.manual_categories[target].category == "Tagesgeld"
    assert "Tagesgeld" not in set(filled.income_expenses("2024-01", "2024-02")[Col.category])
    assert _reloaded(filled).rules[2].category == "Tagesgeld"


def test_import_and_categorization(filled):
    giro = filled.account_transactions("giro")
    assert list(giro[Col.date]) == sorted(giro[Col.date], reverse=True)
    assert dict(zip(giro[Col.recipient], giro[Col.category], strict=True))["EDEKA"] == "household.food"
    assert filled.import_transactions("giro", transactions()) == 0
    assert filled.unique_main_categories() == ["", "household", "income", "spar"]
    assert len(_reloaded(filled).transactions()) == 6


def test_new_main_categories_get_a_group(filled, events):
    """More money in than out: income, otherwise needs; internal transfers get no group."""
    assert [(a.category, a.group) for a in filled.groups] == [
        ("", "needs"),
        ("household", "needs"),
        ("income", "income"),
    ]
    filled.save_rule(Rule(category="hobby.news", regex_recipient="Kiosk"))
    assert GROUPS in events[-1]
    assert "hobby" in [a.category for a in filled.groups]


def test_save_rule_validates_and_replaces(filled, events):
    with pytest.raises(InvalidRuleError) as error:
        filled.save_rule(Rule(regex_recipient="(["))
    assert "regex_recipient" in error.value.errors

    new = Rule(category="household.other")
    assert filled.save_rule(new).id == new.id
    assert filled.rules[-1] == new
    assert events[-1] == frozenset({RULES, TRANSACTIONS})
    copy = filled.save_rule(filled.rules[0])  # saved without original: a new rule
    assert copy.id != filled.rules[0].id
    assert len(filled.rules) == 5

    salary = rule_of(filled, "income")
    saved = filled.save_rule(Rule(category="income.salary", regex_recipient="ACME"), original_id=salary.id)
    assert saved.id == salary.id
    assert [r.category for r in filled.rules][1] == "income.salary"  # keeps its position = priority
    assert "income" not in [r.category for r in filled.rules]
    assert _reloaded(filled).rules[1].category == "income.salary"


def test_update_rule(filled, events):
    salary = rule_of(filled, "income")
    updated = filled.update_rule(salary.id, spread_months=12, residual_percent=10)
    assert (updated.id, updated.spread_months, updated.residual_percent) == (salary.id, 12, 10)
    assert filled.rule(salary.id).regex_recipient == "ACME"
    assert filled.transactions().set_index(Col.recipient).loc["ACME", Col.spread_months] == 12
    count = len(events)
    filled.update_rule(salary.id, spread_months=12)
    assert len(events) == count  # nothing changed, nothing saved
    assert filled.update_rule(salary.id, spread_months=0).residual_percent == 0
    assert filled.update_rule("unknown", category="x") is None


def test_returned_objects_are_copies(filled):
    salary = rule_of(filled, "income")
    filled.rule(salary.id).category = "hacked"
    filled.rules[0].category = "hacked"
    filled.settings.excluded_categories.append("hacked")
    filled.groups[0].group = "wants"
    assert filled.rule(salary.id).category == "income"
    assert filled.rules[0].category == "household.food"
    assert filled.settings.excluded_categories == []
    assert filled.groups[0].group == "needs"


def test_delete_rules(filled, events):
    count = len(events)
    filled.delete_rules(["unknown"])
    assert len(events) == count
    filled.delete_rules([rule_of(filled, "income").id, rule_of(filled, "spar").id])
    assert [r.category for r in filled.rules] == ["household.food"]


def test_manual_categories(filled):
    target = filled.account_transactions("giro").iloc[0][Col.transaction_id]
    filled.save_manual_category(ManualCategory(target, " hobby ", spread_months=24, residual_percent=10))
    row = filled.transaction(target)
    assert (row[Col.category], row[Col.rule], row[Col.spread_months], row[Col.residual_percent]) == (
        "hobby",
        MANUAL_RULE,
        24,
        10,
    )
    assert _reloaded(filled).transaction(target)[Col.category] == "hobby"
    filled.save_manual_category(ManualCategory(target, "hobby", spread_months=0, residual_percent=10))
    assert filled.manual_categories[target].residual_percent == 0  # no residual value without spread
    filled.remove_manual_category(target)
    filled.remove_manual_category(target)
    assert filled.transaction(target)[Col.rule] == ""
    assert filled.transaction("unknown") is None


def test_delete_account_removes_its_manual_categories(filled):
    target = filled.account_transactions("spar").iloc[0][Col.transaction_id]
    filled.save_manual_category(ManualCategory(target, "x"))
    filled.delete_account("spar")
    assert filled.manual_categories == {}


def test_preview_rule(filled):
    kiosk = filled.account_transactions("giro").iloc[0][Col.transaction_id]
    preview = filled.preview_rule(Rule(category="shop", regex_description="Einkauf"), transaction_id=kiosk)
    assert list(preview[Col.recipient]) == ["Kiosk", "EDEKA", "REWE"]
    assert list(preview[Col.category]) == ["", "shop", "shop"]
    # nothing was saved
    assert "shop" not in [r.category for r in filled.rules]


def test_preview_of_edited_rule_ignores_saved_version(filled):
    edited = Rule(category="food", regex_recipient="EDEKA")
    preview = filled.preview_rule(edited, original_id=rule_of(filled, "household.food").id)
    assert list(preview[Col.recipient]) == ["EDEKA"]
    assert filled.preview_rule(Rule(regex_recipient="([")).empty


def test_preview_does_not_override_manual_categories(filled):
    target = filled.account_transactions("giro").iloc[-1][Col.transaction_id]  # REWE
    filled.save_manual_category(ManualCategory(target, "gift"))
    preview = filled.preview_rule(Rule(category="shop", regex_recipient="REWE"))
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
    model.update_settings(excluded_categories=["x"])
    assert events[-1] == frozenset({SETTINGS})
    count = len(events)
    model.update_settings(excluded_categories=["x"])
    assert len(events) == count
    model.set_budget_period(2025, 2023)
    model.set_budget_share("needs", 0.45)
    settings = _reloaded(model).settings
    assert (settings.budget_start, settings.budget_end) == (2023, 2025)
    assert settings.budget_shares["needs"] == 0.45


def test_assign_groups(filled):
    filled.assign_groups({"income": ["income"], "needs": ["household"], "wants": [""]})
    assert [(a.category, a.group) for a in _reloaded(filled).groups] == [
        ("income", "income"),
        ("household", "needs"),
        ("", "wants"),
    ]


def test_income_expenses_respects_settings(filled):
    table = filled.income_expenses("2024-01", "2024-02").set_index(Col.category)
    assert "spar" not in table.index  # transfers hidden by default
    filled.update_settings(hide_internal_transfers=False, excluded_categories=["income"])
    table = filled.income_expenses("2024-01", "2024-02").set_index(Col.category)
    assert "spar" in table.index
    assert "income" not in table.index
    deviation, _ = filled.income_expenses_deviations("2024-01", "2024-02")
    assert list(deviation.columns) == ["2024-01", "2024-02"]


def test_detail(filled):
    detail = filled.detail("2024-01", ["household"])
    assert list(detail[Col.recipient]) == ["REWE", "EDEKA"]
    assert set(detail[Col.account]) == {"giro"}
    total = filled.detail("2024-01", None)
    assert list(total[Col.description]) == ["Einkauf", "Bio Einkauf", "Sparen Eingang", "Gehalt"]  # "Sparen" hidden


def test_budget_and_overview(filled):
    filled.save_rule(Rule(category="giro", regex_description="Sparen Eingang"))  # internal transfer
    filled.set_budget_period(2024, 2024)
    series = filled.budget_series()
    assert "spar" not in series.monthly.columns
    report = filled.budget_report(series)
    assert report.income == 2000.0
    assert report.needs.categories[0] == ("household", 70.0)
    assert report.wants.categories == []
    assert report.savings_rate == pytest.approx((2000 - 72) / 2000)
    assert filled.categories_in_group("income") == ["income"]
    overview = filled.rule_overview().set_index(Col.category)
    assert overview.loc["household.food", "count"] == 2


def test_spread_rule_in_the_budget(filled):
    filled.save_rule(Rule(category="household.bio", regex_description="Bio", spread_months=12, residual_percent=50))
    assert rule_of(filled, "household.bio").residual_percent == 50
    row = filled.transactions().set_index(Col.recipient).loc["EDEKA"]
    assert (row[Col.spread_months], row[Col.residual_percent]) == (12, 50)
    monthly = filled.budget_series().monthly
    # 20 € with 50 % residual value: 10 € over 12 months; the series ends with the last transaction
    assert monthly.loc["2024-02", "household"] == pytest.approx(-10.0 / 12)


def test_sale_of_a_purchase(filled):
    giro = filled.account_transactions("giro").set_index(Col.recipient)
    purchase, salary = giro.loc["REWE", Col.transaction_id], giro.loc["ACME", Col.transaction_id]
    assert filled.sale_candidates(salary).empty  # nothing spread yet
    filled.save_manual_category(ManualCategory(purchase, "hobby.bike", spread_months=36, residual_percent=40))
    candidates = filled.sale_candidates(salary)
    assert list(candidates[Col.transaction_id]) == [purchase]
    assert filled.sale_candidates("unknown").empty

    filled.save_manual_category(ManualCategory(salary, "", sale_of=purchase))
    sale = filled.transaction(salary)
    assert (sale[Col.category], sale[Col.sale_of]) == ("hobby.bike", purchase)  # category of the purchase
    kiosk = filled.account_transactions("giro").iloc[0][Col.transaction_id]
    assert filled.sale_candidates(kiosk).empty  # already sold


def test_uncategorized_count(filled):
    assert filled.uncategorized_count() == 2  # Kiosk and the incoming savings transfer
    filled.save_rule(Rule(category="hobby", regex_recipient="Kiosk"))
    assert filled.uncategorized_count() == 1


def test_backup_restore_reloads_state(filled, tmp_path, events):
    filled.create_backup(tmp_path / "b.zip")
    filled.delete_account("giro")
    previous = filled.restore_backup(tmp_path / "b.zip")
    assert previous is not None
    assert filled.account_names == ["giro", "spar"]
    assert events[-1] == ALL_TOPICS
