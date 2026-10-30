"""Application state and use cases. No Qt in here, so all of it can be tested without a GUI."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain import analysis, budget
from mymoneyvisualizer.domain.categories import category_at_level, unique_categories, unique_main_categories
from mymoneyvisualizer.domain.categorization import RuleMatcher, apply_rules, rule_errors
from mymoneyvisualizer.domain.columns import (
    MANUAL_RULE,
    UNCATEGORIZED,
    Col,
    empty_transactions,
    normalize_transactions,
)
from mymoneyvisualizer.domain.models import (
    GROUP_INCOME,
    GROUP_NEEDS,
    LAST_12_MONTHS,
    GroupAssignment,
    ManualCategory,
    Rule,
    Settings,
    clean_months,
    clean_percent,
    new_rule_id,
    reorder_groups,
    valid_budget_period,
)
from mymoneyvisualizer.importing.profile import ImportProfile
from mymoneyvisualizer.storage.backup import create_backup, restore_backup
from mymoneyvisualizer.storage.repository import Repository

logger = logging.getLogger(__name__)

ACCOUNTS = "accounts"
TRANSACTIONS = "transactions"
RULES = "rules"
GROUPS = "groups"
PROFILES = "profiles"
SETTINGS = "settings"
ALL_TOPICS = frozenset({ACCOUNTS, TRANSACTIONS, RULES, GROUPS, PROFILES, SETTINGS})

DEFAULT_ACCOUNT_NAME = "Neues Konto"


class Event:
    """Minimal observer: ``connect`` handlers, ``emit`` calls all of them."""

    def __init__(self) -> None:
        self._handlers: list[Callable] = []

    def connect(self, handler: Callable) -> None:
        self._handlers.append(handler)

    def disconnect(self, handler: Callable) -> None:
        self._handlers.remove(handler)

    def emit(self, *args) -> None:
        for handler in list(self._handlers):
            handler(*args)


class InvalidRuleError(ValueError):
    def __init__(self, errors: Mapping[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = dict(errors)


def _free_name(base: str, taken: Iterable[str], separator: str = "_", always_number: bool = False) -> str:
    """``base`` if it is free, otherwise ``base_1``, ``base_2``, ..."""
    taken = set(taken)
    if not always_number and base not in taken:
        return base
    n = 1
    while f"{base}{separator}{n}" in taken:
        n += 1
    return f"{base}{separator}{n}"


class AppModel:
    """Owns the state, persists every change immediately and announces it via ``changed(topics)``."""

    def __init__(self, repository: Repository):
        self.repository = repository
        self.changed = Event()
        self._invalidate(raw=True)
        self.reload()

    @classmethod
    def open(cls, data_dir: str | Path) -> AppModel:
        return cls(Repository(data_dir))

    def reload(self) -> None:
        state = self.repository.load()
        self._accounts = state.accounts
        self._rules = state.rules
        self._manual_categories = state.manual_categories
        self._groups = state.groups
        self._profiles = state.profiles
        self._settings = state.settings
        self._invalidate(raw=True)
        self._ensure_groups()
        self.changed.emit(ALL_TOPICS)

    def _invalidate(self, raw: bool = False) -> None:
        """Drop cached results; ``raw`` when transactions were added, removed or moved between accounts."""
        self._categorized: pd.DataFrame | None = None
        self._positions: dict[str, int] | None = None
        self._without: tuple[str, pd.DataFrame] | None = None
        self._later: tuple[str | None, np.ndarray] | None = None
        if raw:
            self._raw: pd.DataFrame | None = None
            self._matcher: RuleMatcher | None = None

    def _notify(self, *topics: str, raw: bool = False) -> None:
        topics = set(topics)
        if raw or TRANSACTIONS in topics or RULES in topics:
            self._invalidate(raw)
            if self._ensure_groups():
                topics.add(GROUPS)
        self.changed.emit(frozenset(topics))

    # ------------------------------------------------------------------ queries
    @property
    def account_names(self) -> list[str]:
        return list(self._accounts)

    @property
    def rules(self) -> list[Rule]:
        return [replace(r) for r in self._rules]

    def rule(self, rule_id: str) -> Rule | None:
        return next((replace(r) for r in self._rules if r.id == rule_id), None)

    @property
    def manual_categories(self) -> dict[str, ManualCategory]:
        return {k: replace(v) for k, v in self._manual_categories.items()}

    @property
    def groups(self) -> list[GroupAssignment]:
        return [replace(a) for a in self._groups]

    @property
    def profiles(self) -> list[ImportProfile]:
        return [replace(p) for p in self._profiles]

    @property
    def settings(self) -> Settings:
        return copy.deepcopy(self._settings)

    def _combined_raw(self) -> pd.DataFrame:
        if self._raw is None:
            frames = [df.assign(**{Col.account: name}) for name, df in self._accounts.items() if not df.empty]
            if frames:
                self._raw = pd.concat(frames, ignore_index=True)
            else:
                self._raw = empty_transactions().assign(**{Col.account: pd.Series(dtype=str)})
        return self._raw

    def _get_matcher(self) -> RuleMatcher:
        """Regex results per distinct text; kept while the transactions stay the same."""
        if self._matcher is None:
            self._matcher = RuleMatcher(self._combined_raw())
        return self._matcher

    def _apply(self, rules: list[Rule]) -> pd.DataFrame:
        return apply_rules(self._combined_raw(), rules, self._manual_categories, self._get_matcher())

    def transactions(self) -> pd.DataFrame:
        """All transactions of all accounts with their categories (cached)."""
        if self._categorized is None:
            self._categorized = self._apply(self._rules)
        return self._categorized

    def account_transactions(self, account: str) -> pd.DataFrame:
        df = self.transactions()
        return df.loc[df[Col.account] == account].sort_values(Col.date, ascending=False, kind="stable")

    def transaction(self, transaction_id: str) -> pd.Series | None:
        df = self.transactions()
        if self._positions is None:
            self._positions = {tid: i for i, tid in enumerate(df[Col.transaction_id])}
        position = self._positions.get(transaction_id)
        return None if position is None else df.iloc[position]

    def unique_categories(self) -> list[str]:
        return unique_categories(self.transactions()[Col.category].unique())

    def unique_main_categories(self) -> list[str]:
        return unique_main_categories(self.transactions()[Col.category].unique())

    # ------------------------------------------------------------------ accounts
    def add_account(self, name: str | None = None) -> str:
        if name is None or not name.strip():
            name = _free_name(DEFAULT_ACCOUNT_NAME, self._accounts, separator=" ", always_number=True)
        else:
            name = _free_name(name.strip(), self._accounts)
        self._accounts[name] = empty_transactions()
        self.repository.save_account(name, self._accounts[name])
        self.repository.save_account_index(self._accounts)
        self._notify(ACCOUNTS, TRANSACTIONS, raw=True)
        return name

    def rename_account(self, old: str, new: str) -> str:
        """Rename an account. Categories of transfers to this account (= old name) are renamed as well."""
        new = new.strip()
        if not new or new == old:
            return old
        new = _free_name(new, [n for n in self._accounts if n != old])
        self.repository.rename_account(old, new)
        self._accounts = {(new if n == old else n): df for n, df in self._accounts.items()}
        self.repository.save_account_index(self._accounts)

        topics = {ACCOUNTS, TRANSACTIONS}
        if any(r.category == old for r in self._rules):
            for rule in self._rules:
                if rule.category == old:
                    rule.category = new
            self.repository.save_rules(self._rules)
            topics.add(RULES)
        if any(m.category == old for m in self._manual_categories.values()):
            for manual in self._manual_categories.values():
                if manual.category == old:
                    manual.category = new
            self.repository.save_manual_categories(self._manual_categories.values())
        self._notify(*topics, raw=True)
        return new

    def delete_account(self, name: str) -> None:
        df = self._accounts.pop(name)
        self.repository.delete_account(name)
        self.repository.save_account_index(self._accounts)
        orphaned = set(df[Col.transaction_id]) & set(self._manual_categories)
        if orphaned:
            for transaction_id in orphaned:
                del self._manual_categories[transaction_id]
            self.repository.save_manual_categories(self._manual_categories.values())
        self._notify(ACCOUNTS, TRANSACTIONS, raw=True)

    def import_transactions(self, account: str, transactions: pd.DataFrame) -> int:
        new = normalize_transactions(transactions)
        if new.empty:
            return 0
        combined = pd.concat([self._accounts[account], new], ignore_index=True)
        self._accounts[account] = combined.sort_values(Col.date, ascending=False, kind="stable").reset_index(drop=True)
        self.repository.save_account(account, self._accounts[account])
        self._notify(TRANSACTIONS, raw=True)
        return len(new)

    # ------------------------------------------------------------------ categorization
    def save_rule(self, rule: Rule, original_id: str | None = None) -> Rule:
        """Replace the rule ``original_id`` (it keeps its id and position) or append a new rule."""
        errors = rule_errors(rule)
        if errors:
            raise InvalidRuleError(errors)
        ids = [r.id for r in self._rules]
        index = ids.index(original_id) if original_id in ids else None
        rule_id = rule.id if index is None else original_id
        if index is None and rule_id in ids:  # a copy of a saved rule becomes a new rule
            rule_id = new_rule_id()
        spread_months = clean_months(rule.spread_months)
        saved = replace(
            rule,
            id=rule_id,
            spread_months=spread_months,
            residual_percent=clean_percent(rule.residual_percent) if spread_months else 0,
        )
        if index is None:
            self._rules.append(saved)
        else:
            self._rules[index] = saved
        self.repository.save_rules(self._rules)
        self._notify(RULES, TRANSACTIONS)
        return replace(saved)

    def update_rule(self, rule_id: str, **changes) -> Rule | None:
        """Change single fields of a rule, e.g. its spread; ``None`` if the rule does not exist (any more)."""
        rule = self.rule(rule_id)
        if rule is None:
            return None
        changed = replace(rule, **changes)
        return rule if changed == rule else self.save_rule(changed, rule_id)

    def delete_rules(self, rule_ids: Iterable[str]) -> None:
        rule_ids = set(rule_ids)
        if not rule_ids & {r.id for r in self._rules}:
            return
        self._rules = [r for r in self._rules if r.id not in rule_ids]
        self.repository.save_rules(self._rules)
        self._notify(RULES, TRANSACTIONS)

    def save_manual_category(self, manual: ManualCategory) -> None:
        """Categorize a single transaction; it wins over the rules.

        The sale of a purchase gets the category of the purchase unless it has one of its own.
        """
        category = manual.category.strip()
        if manual.sale_of and not category:
            purchase = self.transaction(manual.sale_of)
            category = "" if purchase is None else str(purchase[Col.category])
        spread_months = clean_months(manual.spread_months)
        self._manual_categories[manual.transaction_id] = replace(
            manual,
            category=category,
            spread_months=spread_months,
            residual_percent=clean_percent(manual.residual_percent) if spread_months else 0,
        )
        self.repository.save_manual_categories(self._manual_categories.values())
        self._notify(TRANSACTIONS)

    def remove_manual_category(self, transaction_id: str) -> None:
        if self._manual_categories.pop(transaction_id, None) is not None:
            self.repository.save_manual_categories(self._manual_categories.values())
            self._notify(TRANSACTIONS)

    def uncategorized_count(self) -> int:
        return int((self.transactions()[Col.category] == UNCATEGORIZED).sum())

    def sale_candidates(self, transaction_id: str) -> pd.DataFrame:
        """Spread purchases the transaction can be the sale of: not later and not sold by another transaction.

        Newest first.
        """
        df = self.transactions()
        sale = self.transaction(transaction_id)
        if sale is None:
            return df.iloc[0:0]
        others = df[Col.transaction_id] != transaction_id
        sold = set(df.loc[others & (df[Col.sale_of] != ""), Col.sale_of])
        candidates = (
            others
            & (df[Col.spread_months] > 0)
            & (df[Col.value] < 0)
            & (df[Col.date] <= sale[Col.date])
            & ~df[Col.transaction_id].isin(sold)
        )
        return df.loc[candidates].sort_values(Col.date, ascending=False, kind="stable")

    def _categorized_without(self, rule_id: str) -> pd.DataFrame:
        """Categorization without the rule ``rule_id`` (cached while it is edited in the rule window)."""
        if self._without is None or self._without[0] != rule_id:
            self._without = (rule_id, self._apply([r for r in self._rules if r.id != rule_id]))
        return self._without[1]

    def _later_rules_mask(self, rule_id: str | None) -> np.ndarray:
        """Transactions a rule after ``rule_id`` matches: those rules win over it. Nothing comes after a new rule.

        Cached while the rule is edited in the rule window.
        """
        if self._later is None or self._later[0] != rule_id:
            ids = [r.id for r in self._rules]
            mask = np.zeros(len(self._combined_raw()), dtype=bool)
            if rule_id in ids:
                matcher = self._get_matcher()
                for later in self._rules[ids.index(rule_id) + 1 :]:
                    mask |= matcher.mask(later)
            self._later = (rule_id, mask)
        return self._later[1]

    def preview_rule(
        self, rule: Rule, original_id: str | None = None, transaction_id: str | None = None
    ) -> pd.DataFrame:
        """Transactions ``rule`` matches, the transaction ``transaction_id`` first.

        Those the rule categorizes are shown with its category. Those that get their category from a later rule or a
        manual category keep it and name the winner in the column :data:`~analysis.OVERRIDDEN`. The saved version
        ``original_id`` is ignored, so the preview shows exactly what the edited rule does at its position; a new rule
        comes last. Only the patterns of ``rule`` are evaluated, the rest comes from caches: fast enough per key press.
        """
        ids = {r.id for r in self._rules}
        existing = original_id in ids
        base = self._categorized_without(original_id) if existing else self.transactions()
        matched = np.zeros(len(base), dtype=bool) if rule_errors(rule) else self._get_matcher().mask(rule)
        overridden = matched & (
            (base[Col.rule] == MANUAL_RULE).to_numpy() | self._later_rules_mask(original_id if existing else None)
        )
        selected = (
            (base[Col.transaction_id] == transaction_id).to_numpy()
            if transaction_id
            else np.zeros(len(base), dtype=bool)
        )
        shown = selected | matched
        rows = base.loc[shown].copy()
        rows[analysis.OVERRIDDEN] = ""
        taken = overridden[shown]
        rows.loc[taken, analysis.OVERRIDDEN] = rows.loc[taken, Col.rule]
        hit = (matched & ~overridden)[shown]
        rows.loc[hit, Col.category] = rule.category
        rows.loc[hit, Col.rule] = rule.id
        rows.loc[hit, Col.spread_months] = clean_months(rule.spread_months)
        rows.loc[hit, Col.residual_percent] = clean_percent(rule.residual_percent) if rule.spread_months else 0
        first = selected[shown]
        rest = rows.loc[~first].sort_values(Col.date, ascending=False, kind="stable")
        return pd.concat([rows.loc[first], rest]).reset_index(drop=True)

    # ------------------------------------------------------------------ profiles / settings / groups
    def save_profile(self, profile: ImportProfile, original_name: str | None = None) -> ImportProfile:
        """Store an import profile; the most recently used profile is tried first next time."""
        others = [p for p in self._profiles if p.name != original_name]
        name = profile.name.strip() or _free_name("importer", [p.name for p in others], always_number=True)
        saved = replace(profile, name=_free_name(name, [p.name for p in others]))
        self._profiles = [saved, *others]
        self.repository.save_profiles(self._profiles)
        self._notify(PROFILES)
        return replace(saved)

    def update_settings(self, **changes) -> None:
        settings = replace(self._settings, **changes)
        if settings == self._settings:
            return
        self._settings = settings
        self.repository.save_settings(settings)
        self._notify(SETTINGS)

    def set_budget_share(self, group: str, share: float) -> None:
        shares = dict(self._settings.budget_shares)
        shares[group] = share
        self.update_settings(budget_shares=shares)

    def set_budget_period(self, period: str) -> None:
        """:data:`~mymoneyvisualizer.domain.models.LAST_12_MONTHS` or a year such as ``"2025"``."""
        if not valid_budget_period(period):
            raise ValueError(f"invalid budget period {period!r}")
        self.update_settings(budget_period=period)

    def hide_hint(self, name: str) -> None:
        """Do not show the explanation ``name`` again; it stays available behind the help button."""
        if name not in self._settings.hidden_hints:
            self.update_settings(hidden_hints=[*self._settings.hidden_hints, name])

    def assign_groups(self, assignment: Mapping[str, Iterable[str]]) -> None:
        self._groups = reorder_groups(self._groups, {k: list(v) for k, v in assignment.items()})
        self.repository.save_groups(self._groups)
        self._notify(GROUPS)

    def _ensure_groups(self) -> bool:
        """Every main category (except internal transfers) gets a budget group.

        A new main category into which more money comes than goes out is income, any other one needs. Transactions
        without category are needs: unknown spending is treated as necessary until it is categorized.
        """
        known = {a.category for a in self._groups}
        df = self.transactions()
        totals = df[Col.value].groupby(category_at_level(df[Col.category], 0)).sum()
        missing = [c for c in totals.index if c not in known and c not in self._accounts]
        if not missing:
            return False
        self._groups += [
            GroupAssignment(c, GROUP_INCOME if totals[c] > 0 and c != UNCATEGORIZED else GROUP_NEEDS) for c in missing
        ]
        self.repository.save_groups(self._groups)
        return True

    def categories_in_group(self, group: str) -> list[str]:
        """Main categories of a budget group."""
        return [a.category for a in self._groups if a.group == group]

    # ------------------------------------------------------------------ analysis
    def _own_accounts(self, hide: bool = True) -> list[str]:
        return list(self._accounts) if hide else []

    def income_expenses(self, start, end, *, level: int = 0, category_filter: str = "") -> pd.DataFrame | None:
        return analysis.income_expenses_table(
            self.transactions(),
            start,
            end,
            level=level,
            category_filter=category_filter,
            excluded_categories=self._settings.excluded_categories,
            own_accounts=self._own_accounts(self._settings.hide_internal_transfers),
            groups={a.category: a.group for a in self._groups},
        )

    def income_expenses_deviations(self, start, end, *, level: int = 0, category_filter: str = ""):
        return analysis.income_expenses_deviations(
            self.transactions(),
            start,
            end,
            level=level,
            category_filter=category_filter,
            excluded_categories=self._settings.excluded_categories,
            own_accounts=self._own_accounts(self._settings.hide_internal_transfers),
        )

    def detail(self, month, categories: Sequence[str] | None, *, category_filter: str = "") -> pd.DataFrame:
        """Transactions of ``categories`` (``None``: all) in ``month`` (``None``: all months)."""
        return analysis.detail_transactions(
            self.transactions(),
            month,
            categories,
            excluded_categories=self._settings.excluded_categories,
            own_accounts=self._own_accounts(self._settings.hide_internal_transfers),
            category_filter=category_filter,
        )

    def rule_overview(self) -> pd.DataFrame:
        return analysis.rule_overview(self.transactions(), self._rules, self._get_matcher())

    def budget_series(self) -> budget.BudgetSeries:
        return budget.budget_series(
            self.transactions(),
            own_accounts=self._own_accounts(),
            excluded_categories=self._settings.excluded_categories,
        )

    def budget_periods(self, series: budget.BudgetSeries | None = None) -> list[tuple[str, pd.Period, pd.Period]]:
        """``(period, first month, last month)`` of the budget periods with data, newest first.

        The last twelve complete months come first, then every calendar year, cut to the months with data.
        """
        series = series if series is not None else self.budget_series()
        if series.last_date is None:
            return []
        first, last = series.monthly.index[0], analysis.last_complete_month(series.last_date)
        if last < first:
            return []
        periods = [(LAST_12_MONTHS, *budget.period_months(LAST_12_MONTHS, last))]
        for year in range(last.year, first.year - 1, -1):
            start, end = budget.period_months(str(year), last)
            periods.append((str(year), max(start, first), end))
        return periods

    def budget_months(
        self, series: budget.BudgetSeries | None = None, previous: bool = False
    ) -> tuple[pd.Period, pd.Period] | None:
        """First and last month of the budget period (``previous``: of the year before); only complete months."""
        series = series if series is not None else self.budget_series()
        if series.last_date is None:
            return None
        months = budget.period_months(self._settings.budget_period, analysis.last_complete_month(series.last_date))
        return budget.previous_months(*months) if previous else months

    def budget_contributions(
        self, start: pd.Period, end: pd.Period, categories: Sequence[str] | None = None
    ) -> pd.DataFrame:
        """The transactions that count in the budget of ``start`` to ``end``, see :func:`budget.contributions`."""
        return budget.contributions(
            self.transactions(),
            start,
            end,
            own_accounts=self._own_accounts(),
            excluded_categories=self._settings.excluded_categories,
            categories=categories,
        )

    def budget_report(
        self, series: budget.BudgetSeries | None = None, previous: bool = False
    ) -> budget.BudgetReport | None:
        """Income, needs, wants and savings in the budget period (``previous``: in the year before)."""
        series = series if series is not None else self.budget_series()
        months = self.budget_months(series, previous)
        if months is None:
            return None
        return budget.budget_report(series, self._groups, *months, self._settings.budget_shares)

    # ------------------------------------------------------------------ backup
    def create_backup(self, zip_path: str | Path) -> list[str]:
        return create_backup(self.repository.data_dir, zip_path)

    def restore_backup(self, zip_path: str | Path) -> Path | None:
        previous = restore_backup(zip_path, self.repository.data_dir)
        self.reload()
        return previous
