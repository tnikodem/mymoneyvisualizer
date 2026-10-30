"""Load and save the application state.

Layout of the data directory::

    accounts.yaml           list of {name, file}
    accounts/<name>.csv     transaction_id, date, recipient, description, value
    rules.yaml              categorization rules, applied in this order
    manual_categories.yaml  categories of single transactions, win over the rules
    budget_groups.yaml      budget group of every main category
    importers.yaml          import profiles
    configuration.yaml      settings
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from mymoneyvisualizer.domain.columns import RAW_COLUMNS, normalize_transactions
from mymoneyvisualizer.domain.models import GroupAssignment, ManualCategory, Rule, Settings
from mymoneyvisualizer.importing.profile import ImportProfile
from mymoneyvisualizer.storage.files import StorageError, read_csv, read_yaml, write_csv, write_yaml

ACCOUNTS_FILE = "accounts.yaml"
ACCOUNTS_DIR = "accounts"
RULES_FILE = "rules.yaml"
MANUAL_CATEGORIES_FILE = "manual_categories.yaml"
GROUPS_FILE = "budget_groups.yaml"
PROFILES_FILE = "importers.yaml"
SETTINGS_FILE = "configuration.yaml"
DATA_FILES = (ACCOUNTS_FILE, RULES_FILE, MANUAL_CATEGORIES_FILE, GROUPS_FILE, PROFILES_FILE, SETTINGS_FILE)

_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f\s]+')


@dataclass
class State:
    accounts: dict[str, pd.DataFrame] = field(default_factory=dict)
    rules: list[Rule] = field(default_factory=list)
    manual_categories: dict[str, ManualCategory] = field(default_factory=dict)
    groups: list[GroupAssignment] = field(default_factory=list)
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
            rules=[Rule.from_dict(d) for d in _as_list(read_yaml(self.path(RULES_FILE)), RULES_FILE)],
            groups=self._load_groups(),
            profiles=[ImportProfile.from_dict(d) for d in _as_list(read_yaml(self.path(PROFILES_FILE)), PROFILES_FILE)],
        )
        for entry in _as_list(read_yaml(self.path(MANUAL_CATEGORIES_FILE)), MANUAL_CATEGORIES_FILE):
            manual = ManualCategory.from_dict(entry)
            state.manual_categories[manual.transaction_id] = manual

        self._account_files = {}
        for entry in _as_list(read_yaml(self.path(ACCOUNTS_FILE)), ACCOUNTS_FILE):
            name, relative = entry.get("name"), entry.get("file")
            if not name or not relative:
                raise StorageError(f"{ACCOUNTS_FILE}: every account needs a name and a file")
            self._account_files[str(name)] = str(relative)
            state.accounts[str(name)] = self._load_account_file(self.path(str(relative)))
        return state

    def _load_groups(self) -> list[GroupAssignment]:
        groups: dict[str, GroupAssignment] = {}
        for entry in _as_list(read_yaml(self.path(GROUPS_FILE)), GROUPS_FILE):
            assignment = GroupAssignment.from_dict(entry)
            groups.setdefault(assignment.category, assignment)
        return list(groups.values())

    @staticmethod
    def _load_account_file(path: Path) -> pd.DataFrame:
        if not path.is_file():
            return normalize_transactions(pd.DataFrame(columns=list(RAW_COLUMNS)))
        return normalize_transactions(read_csv(path))

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

    def save_rules(self, rules: Iterable[Rule]) -> None:
        write_yaml(self.path(RULES_FILE), [r.to_dict() for r in rules])

    def save_manual_categories(self, manual_categories: Iterable[ManualCategory]) -> None:
        write_yaml(self.path(MANUAL_CATEGORIES_FILE), [m.to_dict() for m in manual_categories])

    def save_groups(self, groups: Iterable[GroupAssignment]) -> None:
        write_yaml(self.path(GROUPS_FILE), [a.to_dict() for a in groups])

    def save_profiles(self, profiles: Iterable[ImportProfile]) -> None:
        write_yaml(self.path(PROFILES_FILE), [p.to_dict() for p in profiles])

    def save_settings(self, settings: Settings) -> None:
        write_yaml(self.path(SETTINGS_FILE), settings.to_dict())

    def save_all(self, state: State) -> None:
        for name, df in state.accounts.items():
            self.save_account(name, df)
        self.save_account_index(state.accounts)
        self.save_rules(state.rules)
        self.save_manual_categories(state.manual_categories.values())
        self.save_groups(state.groups)
        self.save_profiles(state.profiles)
        self.save_settings(state.settings)
