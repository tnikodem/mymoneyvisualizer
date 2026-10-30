"""Application state and use cases. No Qt in here, so all of it can be tested without a GUI."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain import analysis, budget
from mymoneyvisualizer.domain.categories import unique_categories, unique_main_categories
from mymoneyvisualizer.domain.categorization import RuleMatcher, apply_rules, rule_errors
from mymoneyvisualizer.domain.columns import MANUAL_RULE, Col, empty_transactions, normalize_transactions
from mymoneyvisualizer.domain.models import (
    GROUP_NEEDS,
    GroupAssignment,
    ManualCategory,
    Rule,
    Settings,
    clean_recurring,
    recurring_to_float,
    reorder_groups,
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

DEFAULT_ACCOUNT_NAME = "new account"
DEFAULT_RULE_NAME = "new_rule"


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

    def rule(self, name: str) -> Rule | None:
        return next((replace(r) for r in self._rules if r.name == name), None)

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
    def free_rule_name(self, base: str = DEFAULT_RULE_NAME, ignore: str | None = None) -> str:
        taken = {r.name for r in self._rules if r.name != ignore} | {MANUAL_RULE}
        return _free_name(base or DEFAULT_RULE_NAME, taken)

    def save_rule(self, rule: Rule, original_name: str | None = None) -> Rule:
        """Insert a new rule or replace ``original_name``. Names are made unique."""
        errors = rule_errors(rule)
        if errors:
            raise InvalidRuleError(errors)
        names = [r.name for r in self._rules]
        index = names.index(original_name) if original_name in names else None
        saved = replace(
            rule,
            name=self.free_rule_name(rule.name.strip(), ignore=original_name),
            recurring=clean_recurring(rule.recurring),
        )
        if index is None:
            self._rules.append(saved)
        else:
            self._rules[index] = saved
        self.repository.save_rules(self._rules)
        self._notify(RULES, TRANSACTIONS)
        return replace(saved)

    def delete_rules(self, names: Iterable[str]) -> None:
        names = set(names)
        if not names & {r.name for r in self._rules}:
            return
        self._rules = [r for r in self._rules if r.name not in names]
        self.repository.save_rules(self._rules)
        self._notify(RULES, TRANSACTIONS)

    def set_manual_category(self, transaction_id: str, category: str, recurring: int | None = None) -> None:
        self._manual_categories[transaction_id] = ManualCategory(transaction_id, category, clean_recurring(recurring))
        self.repository.save_manual_categories(self._manual_categories.values())
        self._notify(TRANSACTIONS)

    def remove_manual_category(self, transaction_id: str) -> None:
        if self._manual_categories.pop(transaction_id, None) is not None:
            self.repository.save_manual_categories(self._manual_categories.values())
            self._notify(TRANSACTIONS)

    def _categorized_without(self, name: str) -> pd.DataFrame:
        """Categorization without the rule ``name`` (cached while it is edited in the rule window)."""
        if self._without is None or self._without[0] != name:
            self._without = (name, self._apply([r for r in self._rules if r.name != name]))
        return self._without[1]

    def preview_rule(
        self, rule: Rule, original_name: str | None = None, transaction_id: str | None = None
    ) -> pd.DataFrame:
        """Transactions ``rule`` would categorize (shown with its category), the transaction ``transaction_id`` first.

        The saved version ``original_name`` is ignored, so the preview shows exactly what the edited rule does.
        Only the patterns of ``rule`` are evaluated, the rest comes from caches: fast enough per key press.
        """
        names = {r.name for r in self._rules}
        base = self._categorized_without(original_name) if original_name in names else self.transactions()
        if rule_errors(rule):
            matched = np.zeros(len(base), dtype=bool)
        else:
            matched = self._get_matcher().mask(rule) & (base[Col.rule] != MANUAL_RULE).to_numpy()
        selected = (
            (base[Col.transaction_id] == transaction_id).to_numpy()
            if transaction_id
            else np.zeros(len(base), dtype=bool)
        )
        shown = selected | matched
        rows = base.loc[shown].copy()
        hit = matched[shown]
        rows.loc[hit, Col.category] = rule.category
        rows.loc[hit, Col.rule] = rule.name
        rows.loc[hit, Col.recurring] = recurring_to_float(clean_recurring(rule.recurring))
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

    def set_budget_period(self, start: int, end: int) -> None:
        self.update_settings(budget_start=min(start, end), budget_end=max(start, end))

    def assign_groups(self, assignment: Mapping[str, Iterable[str]]) -> None:
        self._groups = reorder_groups(self._groups, {k: list(v) for k, v in assignment.items()})
        self.repository.save_groups(self._groups)
        self._notify(GROUPS)

    def _ensure_groups(self) -> bool:
        """Every main category (except internal transfers) gets a budget group; new ones start as needs."""
        known = {a.category for a in self._groups}
        missing = [t for t in self.unique_main_categories() if t not in known and t not in self._accounts]
        if not missing:
            return False
        self._groups += [GroupAssignment(category, GROUP_NEEDS) for category in missing]
        self.repository.save_groups(self._groups)
        return True

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

    def detail(self, month, category: str | None, *, category_filter: str = "") -> pd.DataFrame:
        return analysis.detail_transactions(
            self.transactions(),
            month,
            category,
            excluded_categories=self._settings.excluded_categories,
            own_accounts=self._own_accounts(self._settings.hide_internal_transfers),
            category_filter=category_filter,
        )

    def rule_overview(self) -> pd.DataFrame:
        return analysis.rule_overview(self.transactions(), self._rules)

    def budget_series(self) -> budget.BudgetSeries:
        return budget.budget_series(
            self.transactions(),
            budget_end_year=self._settings.budget_end,
            own_accounts=self._own_accounts(),
            excluded_categories=self._settings.excluded_categories,
        )

    def budget_report(self, group: str, series: budget.BudgetSeries | None = None) -> budget.BudgetReport | None:
        settings = self._settings
        return budget.budget_report(
            series if series is not None else self.budget_series(),
            self._groups,
            group,
            settings.budget_start,
            settings.budget_end,
            settings.budget_shares[group],
        )

    # ------------------------------------------------------------------ backup
    def create_backup(self, zip_path: str | Path) -> list[str]:
        return create_backup(self.repository.data_dir, zip_path)

    def restore_backup(self, zip_path: str | Path) -> Path | None:
        previous = restore_backup(zip_path, self.repository.data_dir)
        self.reload()
        return previous
