"""Load and save the application state.

Layout of the data directory (compatible with version 0.1)::

    accounts.yaml          list of {name, file}
    accounts/<name>.csv    transaction_id, date, recipient, description, value
    taggers.yaml           tagger rules, applied in this order
    one_time_tags.yaml     tags of single transactions
    tag_categories.yaml    category of every base tag
    importers.yaml         import profiles
    configuration.yaml     settings
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from mymoneyvisualizer.domain.columns import ONE_TIME_TAGGER, RAW_COLUMNS, Col, normalize_transactions
from mymoneyvisualizer.domain.models import OneTimeTag, Settings, TagCategory, Tagger, clean_recurring
from mymoneyvisualizer.importing.profile import ImportProfile
from mymoneyvisualizer.storage.files import StorageError, read_csv, read_yaml, write_csv, write_yaml

logger = logging.getLogger(__name__)

ACCOUNTS_FILE = "accounts.yaml"
ACCOUNTS_DIR = "accounts"
TAGGERS_FILE = "taggers.yaml"
ONE_TIME_TAGS_FILE = "one_time_tags.yaml"
CATEGORIES_FILE = "tag_categories.yaml"
PROFILES_FILE = "importers.yaml"
SETTINGS_FILE = "configuration.yaml"
DATA_FILES = (ACCOUNTS_FILE, TAGGERS_FILE, ONE_TIME_TAGS_FILE, CATEGORIES_FILE, PROFILES_FILE, SETTINGS_FILE)

_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f\s]+')


@dataclass
class State:
    accounts: dict[str, pd.DataFrame] = field(default_factory=dict)
    taggers: list[Tagger] = field(default_factory=list)
    one_time_tags: dict[str, OneTimeTag] = field(default_factory=dict)
    categories: list[TagCategory] = field(default_factory=list)
    profiles: list[ImportProfile] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)


def account_file_name(name: str, taken: Iterable[str] = ()) -> str:
    """Relative CSV path for an account, unique among ``taken``."""
    stem = _INVALID_FILENAME.sub("_", name).strip("._") or "account"
    taken = {t.lower() for t in taken}
    candidate, n = f"{ACCOUNTS_DIR}/{stem}.csv", 2
    while candidate.lower() in taken:
        candidate, n = f"{ACCOUNTS_DIR}/{stem}_{n}.csv", n + 1
    return candidate


def _as_list(data: object, path: str) -> list[Mapping]:
    if data is None:
        return []
    if not isinstance(data, list) or not all(isinstance(item, Mapping) for item in data):
        raise StorageError(f"{path} must contain a list of entries")
    return data


class Repository:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._account_files: dict[str, str] = {}

    def path(self, relative: str) -> Path:
        return self.data_dir / relative

    # ------------------------------------------------------------------ load
    def load(self) -> State:
        state = State(
            settings=Settings.from_dict(read_yaml(self.path(SETTINGS_FILE))),
            taggers=[Tagger.from_dict(d) for d in _as_list(read_yaml(self.path(TAGGERS_FILE)), TAGGERS_FILE)],
            categories=self._load_categories(),
            profiles=[ImportProfile.from_dict(d) for d in _as_list(read_yaml(self.path(PROFILES_FILE)), PROFILES_FILE)],
        )
        for entry in _as_list(read_yaml(self.path(ONE_TIME_TAGS_FILE)), ONE_TIME_TAGS_FILE):
            tag = OneTimeTag.from_dict(entry)
            state.one_time_tags[tag.transaction_id] = tag

        migrated_tags = False
        self._account_files = {}
        for entry in _as_list(read_yaml(self.path(ACCOUNTS_FILE)), ACCOUNTS_FILE):
            name = str(entry.get("name", "")).strip()
            if not name or name in state.accounts:
                continue
            relative, legacy = self._account_location(entry)
            self._account_files[name] = relative
            df, one_time, needs_rewrite = self._load_account_file(legacy or self.path(relative))
            for tag in one_time:
                if tag.transaction_id not in state.one_time_tags:
                    state.one_time_tags[tag.transaction_id] = tag
                    migrated_tags = True
            state.accounts[name] = df
            if needs_rewrite or legacy is not None:
                logger.info("migrating account file of %s to %s", name, relative)
                self.save_account(name, df)

        if migrated_tags:
            self.save_one_time_tags(state.one_time_tags.values())
        if (self.path(ACCOUNTS_FILE).is_file() and self._accounts_file_is_legacy()) or migrated_tags:
            self.save_account_index(state.accounts)
        return state

    def _load_categories(self) -> list[TagCategory]:
        categories: dict[str, TagCategory] = {}
        for entry in _as_list(read_yaml(self.path(CATEGORIES_FILE)), CATEGORIES_FILE):
            category = TagCategory.from_dict(entry)
            categories.setdefault(category.name, category)
        return list(categories.values())

    def _account_location(self, entry: Mapping) -> tuple[str, Path | None]:
        """Relative file of an account; for version 0.1 entries also the existing legacy file (if any)."""
        if entry.get("file"):
            return str(entry["file"]).replace("\\", "/"), None
        taken = set(self._account_files.values())
        relative = account_file_name(str(entry["name"]), taken)
        legacy = entry.get("db_filepath")
        if not legacy:
            return relative, None
        legacy = Path(str(legacy))
        # files inside this data directory first: an old backup must not pick up the live ./config files
        candidates = [self.path(ACCOUNTS_DIR) / legacy.name, legacy if legacy.is_absolute() else Path.cwd() / legacy]
        for candidate in candidates:
            if candidate.is_file():
                return relative, candidate
        return relative, None

    def _accounts_file_is_legacy(self) -> bool:
        entries = _as_list(read_yaml(self.path(ACCOUNTS_FILE)), ACCOUNTS_FILE)
        return any("file" not in e for e in entries)

    @staticmethod
    def _load_account_file(path: Path) -> tuple[pd.DataFrame, list[OneTimeTag], bool]:
        """``(transactions, one_time_tags, needs_rewrite)``; old files also stored the derived tag columns."""
        if not path.is_file():
            return normalize_transactions(pd.DataFrame(columns=list(RAW_COLUMNS))), [], False
        raw = read_csv(path)
        one_time: list[OneTimeTag] = []
        if Col.tagger_name in raw.columns and Col.transaction_id in raw.columns:
            rows = raw.loc[raw[Col.tagger_name] == ONE_TIME_TAGGER]
            for _, row in rows.iterrows():
                if row[Col.transaction_id]:
                    one_time.append(
                        OneTimeTag(
                            transaction_id=row[Col.transaction_id],
                            tag=str(row.get(Col.tag, "")).strip(),
                            recurring=clean_recurring(row.get(Col.recurring)),
                        )
                    )
        missing_ids = Col.transaction_id not in raw.columns or (raw[Col.transaction_id] == "").any()
        df = normalize_transactions(raw)
        needs_rewrite = missing_ids or list(raw.columns) != list(RAW_COLUMNS)
        return df, one_time, needs_rewrite

    # ------------------------------------------------------------------ save
    def save_account_index(self, names: Iterable[str]) -> None:
        names = list(names)
        for name in names:
            if name not in self._account_files:
                self._account_files[name] = account_file_name(name, self._account_files.values())
        write_yaml(self.path(ACCOUNTS_FILE), [{"name": n, "file": self._account_files[n]} for n in names])

    def save_account(self, name: str, df: pd.DataFrame) -> None:
        if name not in self._account_files:
            self._account_files[name] = account_file_name(name, self._account_files.values())
        write_csv(self.path(self._account_files[name]), df[list(RAW_COLUMNS)])

    def account_file(self, name: str) -> Path:
        return self.path(self._account_files[name])

    def rename_account(self, old: str, new: str) -> None:
        """Rename the CSV file of an account; the caller saves the index afterwards."""
        old_relative = self._account_files.pop(old)
        new_relative = account_file_name(new, self._account_files.values())
        old_path, new_path = self.path(old_relative), self.path(new_relative)
        if old_path.is_file() and old_path != new_path:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.replace(new_path)
        self._account_files[new] = new_relative

    def delete_account(self, name: str) -> None:
        relative = self._account_files.pop(name, None)
        if relative is not None:
            self.path(relative).unlink(missing_ok=True)

    def save_taggers(self, taggers: Iterable[Tagger]) -> None:
        write_yaml(self.path(TAGGERS_FILE), [t.to_dict() for t in taggers])

    def save_one_time_tags(self, tags: Iterable[OneTimeTag]) -> None:
        write_yaml(self.path(ONE_TIME_TAGS_FILE), [t.to_dict() for t in tags])

    def save_categories(self, categories: Iterable[TagCategory]) -> None:
        write_yaml(self.path(CATEGORIES_FILE), [c.to_dict() for c in categories])

    def save_profiles(self, profiles: Iterable[ImportProfile]) -> None:
        write_yaml(self.path(PROFILES_FILE), [p.to_dict() for p in profiles])

    def save_settings(self, settings: Settings) -> None:
        write_yaml(self.path(SETTINGS_FILE), settings.to_dict())

    def save_all(self, state: State) -> None:
        for name, df in state.accounts.items():
            self.save_account(name, df)
        self.save_account_index(state.accounts)
        self.save_taggers(state.taggers)
        self.save_one_time_tags(state.one_time_tags.values())
        self.save_categories(state.categories)
        self.save_profiles(state.profiles)
        self.save_settings(state.settings)
