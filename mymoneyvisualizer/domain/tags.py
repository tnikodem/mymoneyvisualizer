"""Helpers for hierarchical tags such as ``household.food.grocery``."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from mymoneyvisualizer.domain.columns import UNTAGGED

SEPARATOR = "."
UNTAGGED_LABEL = "(no tag)"


def base_tag(tag: str) -> str:
    return str(tag).split(SEPARATOR, 1)[0]


def tag_at_level(tags: pd.Series, level: int) -> pd.Series:
    """Cut tags to ``level + 1`` parts; level 0 is the base tag."""
    if level < 0:
        raise ValueError("level must be >= 0")
    parts = tags.astype(str).str.split(SEPARATOR, n=level + 1)
    return parts.str[: level + 1].str.join(SEPARATOR)


def matches_tag(tags: pd.Series, tag: str) -> pd.Series:
    """True for ``tag`` itself and all of its sub tags, but not for tags that merely share a prefix.

    ``car`` matches ``car`` and ``car.fuel`` but not ``carsharing``.
    """
    tags = tags.astype(str)
    if tag == UNTAGGED:
        return tags == UNTAGGED
    return (tags == tag) | tags.str.startswith(tag + SEPARATOR)


def unique_tags(tags: Iterable[str]) -> list[str]:
    return sorted({str(t) for t in tags})


def unique_base_tags(tags: Iterable[str]) -> list[str]:
    return sorted({base_tag(t) for t in tags})


def display_tag(tag: str) -> str:
    return UNTAGGED_LABEL if tag == UNTAGGED else tag
