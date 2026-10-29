"""Application state and use cases. No Qt in here, so all of it can be tested without a GUI."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from pathlib import Path

import pandas as pd

from mymoneyvisualizer.domain import analysis, budget
from mymoneyvisualizer.domain.columns import ONE_TIME_TAGGER, Col, empty_transactions, normalize_transactions
from mymoneyvisualizer.domain.models import (
    CATEGORY_BASIC,
    OneTimeTag,
    Settings,
    TagCategory,
    Tagger,
    clean_recurring,
    recurring_to_float,
    reorder_categories,
)
from mymoneyvisualizer.domain.tagging import apply_taggers, tagger_errors, tagger_mask
from mymoneyvisualizer.domain.tags import unique_base_tags, unique_tags
from mymoneyvisualizer.importing.profile import ImportProfile
from mymoneyvisualizer.storage.backup import create_backup, restore_backup
from mymoneyvisualizer.storage.repository import Repository

logger = logging.getLogger(__name__)

ACCOUNTS = "accounts"
TRANSACTIONS = "transactions"
TAGGERS = "taggers"
CATEGORIES = "categories"
PROFILES = "profiles"
SETTINGS = "settings"
ALL_TOPICS = frozenset({ACCOUNTS, TRANSACTIONS, TAGGERS, CATEGORIES, PROFILES, SETTINGS})

DEFAULT_ACCOUNT_NAME = "new account"
DEFAULT_TAGGER_NAME = "new_tagger"


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


class InvalidTaggerError(ValueError):
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
        self._tagged: pd.DataFrame | None = None
        self.reload()

    @classmethod
    def open(cls, data_dir: str | Path) -> AppModel:
        return cls(Repository(data_dir))

    def reload(self) -> None:
        state = self.repository.load()
        self._accounts = state.accounts
        self._taggers = state.taggers
        self._one_time_tags = state.one_time_tags
        self._categories = state.categories
        self._profiles = state.profiles
        self._settings = state.settings
        self._tagged = None
        self._ensure_categories()
        self.changed.emit(ALL_TOPICS)

    def _notify(self, *topics: str) -> None:
        topics = set(topics)
        if TRANSACTIONS in topics or TAGGERS in topics:
            self._tagged = None
            if self._ensure_categories():
                topics.add(CATEGORIES)
        self.changed.emit(frozenset(topics))

    # ------------------------------------------------------------------ queries
    @property
    def account_names(self) -> list[str]:
        return list(self._accounts)

    @property
    def taggers(self) -> list[Tagger]:
        return [replace(t) for t in self._taggers]

    def tagger(self, name: str) -> Tagger | None:
        return next((replace(t) for t in self._taggers if t.name == name), None)

    @property
    def one_time_tags(self) -> dict[str, OneTimeTag]:
        return {k: replace(v) for k, v in self._one_time_tags.items()}

    @property
    def categories(self) -> list[TagCategory]:
        return [replace(c) for c in self._categories]

    @property
    def profiles(self) -> list[ImportProfile]:
        return [replace(p) for p in self._profiles]

    @property
    def settings(self) -> Settings:
        return copy.deepcopy(self._settings)

    def _combined_raw(self) -> pd.DataFrame:
        frames = [df.assign(**{Col.account: name}) for name, df in self._accounts.items() if not df.empty]
        if not frames:
            return empty_transactions().assign(**{Col.account: pd.Series(dtype=str)})
        return pd.concat(frames, ignore_index=True)

    def transactions(self) -> pd.DataFrame:
        """All transactions of all accounts with their tags (cached)."""
        if self._tagged is None:
            self._tagged = apply_taggers(self._combined_raw(), self._taggers, self._one_time_tags)
        return self._tagged

    def account_transactions(self, account: str) -> pd.DataFrame:
        df = self.transactions()
        return df.loc[df[Col.account] == account].sort_values(Col.date, ascending=False, kind="stable")

    def transaction(self, transaction_id: str) -> pd.Series | None:
        df = self.transactions()
        rows = df.loc[df[Col.transaction_id] == transaction_id]
        return None if rows.empty else rows.iloc[0]

    def unique_tags(self) -> list[str]:
        return unique_tags(self.transactions()[Col.tag])

    def unique_base_tags(self) -> list[str]:
        return unique_base_tags(self.transactions()[Col.tag])

    # ------------------------------------------------------------------ accounts
    def add_account(self, name: str | None = None) -> str:
        if name is None or not name.strip():
            name = _free_name(DEFAULT_ACCOUNT_NAME, self._accounts, separator=" ", always_number=True)
        else:
            name = _free_name(name.strip(), self._accounts)
        self._accounts[name] = empty_transactions()
        self.repository.save_account(name, self._accounts[name])
        self.repository.save_account_index(self._accounts)
        self._notify(ACCOUNTS, TRANSACTIONS)
        return name

    def rename_account(self, old: str, new: str) -> str:
        """Rename an account. Tags of transfers to this account (= old name) are renamed as well."""
        new = new.strip()
        if not new or new == old:
            return old
        new = _free_name(new, [n for n in self._accounts if n != old])
        self.repository.rename_account(old, new)
        self._accounts = {(new if n == old else n): df for n, df in self._accounts.items()}
        self.repository.save_account_index(self._accounts)

        topics = {ACCOUNTS, TRANSACTIONS}
        if any(t.tag == old for t in self._taggers):
            for tagger in self._taggers:
                if tagger.tag == old:
                    tagger.tag = new
            self.repository.save_taggers(self._taggers)
            topics.add(TAGGERS)
        if any(t.tag == old for t in self._one_time_tags.values()):
            for tag in self._one_time_tags.values():
                if tag.tag == old:
                    tag.tag = new
            self.repository.save_one_time_tags(self._one_time_tags.values())
        self._notify(*topics)
        return new

    def delete_account(self, name: str) -> None:
        df = self._accounts.pop(name)
        self.repository.delete_account(name)
        self.repository.save_account_index(self._accounts)
        orphaned = set(df[Col.transaction_id]) & set(self._one_time_tags)
        if orphaned:
            for transaction_id in orphaned:
                del self._one_time_tags[transaction_id]
            self.repository.save_one_time_tags(self._one_time_tags.values())
        self._notify(ACCOUNTS, TRANSACTIONS)

    def import_transactions(self, account: str, transactions: pd.DataFrame) -> int:
        new = normalize_transactions(transactions)
        if new.empty:
            return 0
        combined = pd.concat([self._accounts[account], new], ignore_index=True)
        self._accounts[account] = combined.sort_values(Col.date, ascending=False, kind="stable").reset_index(drop=True)
        self.repository.save_account(account, self._accounts[account])
        self._notify(TRANSACTIONS)
        return len(new)

    # ------------------------------------------------------------------ tagging
    def free_tagger_name(self, base: str = DEFAULT_TAGGER_NAME, ignore: str | None = None) -> str:
        taken = {t.name for t in self._taggers if t.name != ignore} | {ONE_TIME_TAGGER}
        return _free_name(base or DEFAULT_TAGGER_NAME, taken)

    def save_tagger(self, tagger: Tagger, original_name: str | None = None) -> Tagger:
        """Insert a new tagger or replace ``original_name``. Names are made unique."""
        errors = tagger_errors(tagger)
        if errors:
            raise InvalidTaggerError(errors)
        names = [t.name for t in self._taggers]
        index = names.index(original_name) if original_name in names else None
        saved = replace(
            tagger,
            name=self.free_tagger_name(tagger.name.strip(), ignore=original_name),
            recurring=clean_recurring(tagger.recurring),
        )
        if index is None:
            self._taggers.append(saved)
        else:
            self._taggers[index] = saved
        self.repository.save_taggers(self._taggers)
        self._notify(TAGGERS, TRANSACTIONS)
        return replace(saved)

    def delete_taggers(self, names: Iterable[str]) -> None:
        names = set(names)
        if not names & {t.name for t in self._taggers}:
            return
        self._taggers = [t for t in self._taggers if t.name not in names]
        self.repository.save_taggers(self._taggers)
        self._notify(TAGGERS, TRANSACTIONS)

    def set_one_time_tag(self, transaction_id: str, tag: str, recurring: int | None = None) -> None:
        self._one_time_tags[transaction_id] = OneTimeTag(transaction_id, tag, clean_recurring(recurring))
        self.repository.save_one_time_tags(self._one_time_tags.values())
        self._notify(TRANSACTIONS)

    def remove_one_time_tag(self, transaction_id: str) -> None:
        if self._one_time_tags.pop(transaction_id, None) is not None:
            self.repository.save_one_time_tags(self._one_time_tags.values())
            self._notify(TRANSACTIONS)

    def preview_tagger(
        self, tagger: Tagger, original_name: str | None = None, transaction_id: str | None = None
    ) -> pd.DataFrame:
        """Transactions ``tagger`` would tag (shown with its tag), the transaction ``transaction_id`` first.

        The saved version ``original_name`` is ignored, so the preview shows exactly what the edited rule does.
        """
        others = [t for t in self._taggers if t.name != original_name]
        df = apply_taggers(self._combined_raw(), others, self._one_time_tags)
        matched = tagger_mask(df, tagger) if not tagger_errors(tagger) else pd.Series(False, index=df.index)
        matched &= df[Col.tagger_name] != ONE_TIME_TAGGER
        df.loc[matched, Col.tag] = tagger.tag
        df.loc[matched, Col.tagger_name] = tagger.name
        df.loc[matched, Col.recurring] = recurring_to_float(clean_recurring(tagger.recurring))
        selected = df[Col.transaction_id] == transaction_id if transaction_id else pd.Series(False, index=df.index)
        result = pd.concat(
            [df.loc[selected], df.loc[matched & ~selected].sort_values(Col.date, ascending=False, kind="stable")]
        )
        return result.reset_index(drop=True)

    # ------------------------------------------------------------------ profiles / settings / categories
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

    def set_budget_factor(self, category: str, factor: float) -> None:
        factors = dict(self._settings.budget_factors)
        factors[category] = factor
        self.update_settings(budget_factors=factors)

    def set_budget_period(self, start: int, end: int) -> None:
        self.update_settings(budget_start=min(start, end), budget_end=max(start, end))

    def assign_categories(self, assignment: Mapping[str, Iterable[str]]) -> None:
        self._categories = reorder_categories(self._categories, {k: list(v) for k, v in assignment.items()})
        self.repository.save_categories(self._categories)
        self._notify(CATEGORIES)

    def _ensure_categories(self) -> bool:
        """Every base tag (except transfers) gets a category; new ones start as basic expenses."""
        known = {c.name for c in self._categories}
        missing = [t for t in self.unique_base_tags() if t not in known and t not in self._accounts]
        if not missing:
            return False
        self._categories += [TagCategory(name, CATEGORY_BASIC) for name in missing]
        self.repository.save_categories(self._categories)
        return True

    # ------------------------------------------------------------------ analysis
    def _transfers(self, hide: bool = True) -> list[str]:
        return list(self._accounts) if hide else []

    def summary(self, start, end, *, tag_level: int = 0, tag_filter: str = "") -> pd.DataFrame | None:
        return analysis.summary_table(
            self.transactions(),
            start,
            end,
            tag_level=tag_level,
            tag_filter=tag_filter,
            excluded_tags=self._settings.excluded_tags,
            transfer_accounts=self._transfers(self._settings.hide_transfers),
        )

    def summary_deviations(self, start, end, *, tag_level: int = 0, tag_filter: str = ""):
        return analysis.summary_deviations(
            self.transactions(),
            start,
            end,
            tag_level=tag_level,
            tag_filter=tag_filter,
            excluded_tags=self._settings.excluded_tags,
            transfer_accounts=self._transfers(self._settings.hide_transfers),
        )

    def detail(self, month, tag: str | None, *, tag_filter: str = "") -> pd.DataFrame:
        return analysis.detail_transactions(
            self.transactions(),
            month,
            tag,
            excluded_tags=self._settings.excluded_tags,
            transfer_accounts=self._transfers(self._settings.hide_transfers),
            tag_filter=tag_filter,
        )

    def tagger_overview(self) -> pd.DataFrame:
        return analysis.tagger_overview(self.transactions(), self._taggers)

    def budget_series(self) -> budget.BudgetSeries:
        return budget.budget_series(
            self.transactions(),
            budget_end_year=self._settings.budget_end,
            transfer_accounts=self._transfers(),
            excluded_tags=self._settings.excluded_tags,
        )

    def budget_report(self, category: str, series: budget.BudgetSeries | None = None) -> budget.BudgetReport | None:
        settings = self._settings
        return budget.budget_report(
            series if series is not None else self.budget_series(),
            self._categories,
            category,
            settings.budget_start,
            settings.budget_end,
            settings.budget_factors[category],
        )

    # ------------------------------------------------------------------ backup
    def create_backup(self, zip_path: str | Path) -> list[str]:
        return create_backup(self.repository.data_dir, zip_path)

    def restore_backup(self, zip_path: str | Path) -> Path | None:
        previous = restore_backup(zip_path, self.repository.data_dir)
        self.reload()
        return previous
