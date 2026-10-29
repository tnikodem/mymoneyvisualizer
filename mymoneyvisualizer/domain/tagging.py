"""Derive tag columns from tagger rules and one-time tags."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain.columns import ONE_TIME_TAGGER, UNTAGGED, Col
from mymoneyvisualizer.domain.models import OneTimeTag, Tagger, recurring_to_float

logger = logging.getLogger(__name__)


def regex_error(pattern: str) -> str | None:
    """Error message if ``pattern`` is not a valid regular expression."""
    try:
        re.compile(pattern)
    except re.error as e:
        return str(e)
    return None


def tagger_errors(tagger: Tagger) -> dict[str, str]:
    errors = {}
    for field_name in ("regex_recipient", "regex_description"):
        error = regex_error(getattr(tagger, field_name))
        if error is not None:
            errors[field_name] = error
    return errors


def tagger_mask(df: pd.DataFrame, tagger: Tagger) -> pd.Series:
    """Rows matched by ``tagger``. Empty regexes match everything; regexes are searched, not anchored."""
    mask = pd.Series(True, index=df.index)
    for column, pattern in ((Col.recipient, tagger.regex_recipient), (Col.description, tagger.regex_description)):
        if not pattern:
            continue
        try:
            mask &= df[column].astype(str).str.contains(pattern, regex=True, na=False)
        except re.error as e:
            logger.error("tagger %r has an invalid regex %r: %s", tagger.name, pattern, e)
            return pd.Series(False, index=df.index)
    return mask


def tagger_matches(tagger: Tagger, recipient: str, description: str) -> tuple[bool, bool]:
    """Whether the recipient and description regex of ``tagger`` match a single transaction."""
    row = pd.DataFrame({Col.recipient: [recipient], Col.description: [description]})
    recipient_only = Tagger(name=tagger.name, regex_recipient=tagger.regex_recipient)
    description_only = Tagger(name=tagger.name, regex_description=tagger.regex_description)
    return bool(tagger_mask(row, recipient_only).iloc[0]), bool(tagger_mask(row, description_only).iloc[0])


def apply_taggers(
    transactions: pd.DataFrame,
    taggers: Iterable[Tagger],
    one_time_tags: Mapping[str, OneTimeTag] | None = None,
) -> pd.DataFrame:
    """Return a copy of ``transactions`` with ``tag``, ``tagger_name`` and ``recurring`` columns.

    Taggers are applied in order; a later tagger overwrites an earlier one. One-time tags win over all taggers.
    """
    df = transactions.copy()
    df[Col.tag] = UNTAGGED
    df[Col.tagger_name] = ""
    df[Col.recurring] = np.nan
    for tagger in taggers:
        mask = tagger_mask(df, tagger)
        if mask.any():
            df.loc[mask, Col.tag] = tagger.tag
            df.loc[mask, Col.tagger_name] = tagger.name
            df.loc[mask, Col.recurring] = recurring_to_float(tagger.recurring)

    if one_time_tags:
        mask = df[Col.transaction_id].isin(list(one_time_tags))
        if mask.any():
            ids = df.loc[mask, Col.transaction_id]
            df.loc[mask, Col.tag] = [one_time_tags[i].tag for i in ids]
            df.loc[mask, Col.tagger_name] = ONE_TIME_TAGGER
            df.loc[mask, Col.recurring] = [recurring_to_float(one_time_tags[i].recurring) for i in ids]
    return df
