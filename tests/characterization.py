"""Loader for the characterization data set (see ``tests/data/characterization``)."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from mymoneyvisualizer.domain.columns import Col, normalize_transactions
from mymoneyvisualizer.domain.models import OneTimeTag, TagCategory, Tagger
from mymoneyvisualizer.domain.tagging import apply_taggers

DATA_DIR = Path(__file__).parent / "data" / "characterization"


@dataclass
class Dataset:
    raw: dict[str, pd.DataFrame]
    taggers: list[Tagger]
    one_time_tags: dict[str, OneTimeTag]
    categories: list[TagCategory]
    tagged: pd.DataFrame

    @property
    def account_names(self) -> list[str]:
        return list(self.raw)


def _yaml(name):
    return yaml.safe_load((DATA_DIR / name).read_text(encoding="utf-8"))


def load_dataset() -> Dataset:
    transactions = pd.read_csv(DATA_DIR / "transactions.csv", keep_default_na=False)
    raw = {
        name: normalize_transactions(group.drop(columns=Col.account))
        for name, group in transactions.groupby(Col.account, sort=False)
    }
    taggers = [Tagger.from_dict(d) for d in _yaml("taggers.yaml")]
    one_time = {o.transaction_id: o for o in (OneTimeTag.from_dict(d) for d in _yaml("one_time_tags.yaml"))}
    categories = [TagCategory.from_dict(d) for d in _yaml("tag_categories.yaml")]
    combined = pd.concat([df.assign(**{Col.account: name}) for name, df in raw.items()], ignore_index=True)
    return Dataset(raw, taggers, one_time, categories, apply_taggers(combined, taggers, one_time))
