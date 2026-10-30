"""Derive tag columns from tagger rules and one-time tags."""

from __future__ import annotations

import bisect
import itertools
import logging
import re
from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain.columns import ONE_TIME_TAGGER, UNTAGGED, Col
from mymoneyvisualizer.domain.models import OneTimeTag, Tagger, recurring_to_float

logger = logging.getLogger(__name__)


def regex_for(text: str) -> str:
    """Regex matching ``text`` literally, also if it contains broken characters (``�``, ``Ã¤``).

    Single spaces stay readable; other whitespace (line breaks, tabs, several spaces, U+2028) matches any
    whitespace, because a line edit cannot hold line breaks.
    """
    return "".join(
        (" " if part == " " else r"\s+") if part.isspace() else re.escape(part)
        for part in re.split(r"(\s+)", text.strip())
        if part
    )


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


def anchored_literals(pattern: str) -> list[tuple[str, bool, bool]] | None:
    """``(text, at_start, at_end)`` per alternative of a pattern made of plain text, ``^`` and ``$`` only.

    ``^REWE|Shell 12$`` -> ``[("REWE", True, False), ("Shell 12", False, True)]``. ``None`` if the pattern uses
    other regex syntax; escaped characters (as written by :func:`re.escape`) are plain text.
    """
    parts: list[tuple[str, bool, bool]] = []
    current: list[str] = []
    at_start = at_end = False
    i = 0
    while i <= len(pattern):
        char = pattern[i] if i < len(pattern) else "|"
        if at_end and char != "|":
            return None  # "$" in the middle
        if char == "\\":
            if i + 1 == len(pattern) or pattern[i + 1].isalnum() or pattern[i + 1] == "_":
                return None  # \d, \s, \1, ...
            current.append(pattern[i + 1])
            i += 2
            continue
        if char == "|":
            parts.append(("".join(current), at_start, at_end))
            current, at_start, at_end = [], False, False
        elif char == "^" and not current and not at_start:
            at_start = True
        elif char == "$":
            at_end = True
        elif char in ".^*+?{}[]()":
            return None
        else:
            current.append(char)
        i += 1
    return parts


def literal_alternatives(pattern: str) -> list[str] | None:
    """The plain texts of a pattern without anchors (``REWE|EDEKA\\.de`` -> ``["REWE", "EDEKA.de"]``)."""
    parts = anchored_literals(pattern)
    if parts is None or any(at_start or at_end for _, at_start, at_end in parts):
        return None
    return [text for text, _, _ in parts]


_SEPARATOR = "\x1f"


class _DistinctTexts:
    """The distinct values of a text column, also joined to one string for fast substring searches.

    ``joined`` is ``SEP value0 SEP value1 ... SEP``, so ``SEP + text`` finds values starting with ``text`` and
    ``text + SEP`` values ending with it.
    """

    def __init__(self, values: pd.Series):
        codes, uniques = pd.factorize(values.astype(str).to_numpy(dtype=object))
        self.codes = codes
        self.values = [str(v) for v in uniques]
        self.joined = _SEPARATOR + _SEPARATOR.join(self.values) + _SEPARATOR
        self.starts = list(itertools.accumulate((len(v) + 1 for v in self.values), initial=1))[:-1]
        # with the separator inside a value, "SEP + text" no longer means "value starts with text"
        self.separator_free = self.joined.count(_SEPARATOR) == len(self.values) + 1

    def find(self, needle: str, shift: int = 0) -> np.ndarray:
        """Values containing ``needle``; ``shift`` = number of leading separators in ``needle`` (0 or 1)."""
        found = np.zeros(len(self.values), dtype=bool)
        starts, find = self.starts, self.joined.find
        position = find(needle)
        while position >= 0:
            index = bisect.bisect_right(starts, position + shift) - 1
            found[index] = True
            if index + 1 == len(starts):
                break
            position = find(needle, starts[index + 1] - shift)
        return found

    def search(self, pattern: str) -> np.ndarray:
        """Like ``re.search`` on every value."""
        parts = anchored_literals(pattern)
        anchored = parts is not None and any(at_start or at_end for _, at_start, at_end in parts)
        if (
            parts is not None
            and not any(_SEPARATOR in text for text, _, _ in parts)
            and (self.separator_free or not anchored)
        ):
            found = np.zeros(len(self.values), dtype=bool)
            for text, at_start, at_end in parts:
                if not text and not at_start and not at_end:
                    return np.ones(len(self.values), dtype=bool)
                prefix = _SEPARATOR if at_start else ""
                found |= self.find(prefix + text + (_SEPARATOR if at_end else ""), len(prefix))
                if at_end:  # like re: "$" also matches before a newline at the very end
                    found |= self.find(prefix + text + "\n" + _SEPARATOR, len(prefix))
            return found
        search = re.compile(pattern).search
        return np.fromiter((search(v) is not None for v in self.values), dtype=bool, count=len(self.values))


class TagMatcher:
    """Finds the transactions a tagger matches, fast enough for tens of thousands of transactions.

    Every regex is evaluated once per *distinct* recipient / description and the result is cached, so a
    changed tagger only costs the evaluation of its own patterns. Plain text patterns (e.g. taggers created by
    double click) are found by a substring search in one joined string instead of one regex call per value.
    """

    CACHE_LIMIT = 20_000

    def __init__(self, transactions: pd.DataFrame):
        self.size = len(transactions)
        self._texts = {column: _DistinctTexts(transactions[column]) for column in (Col.recipient, Col.description)}
        self._cache: dict[tuple[str, str], np.ndarray] = {}

    def distinct_matches(self, column: str, pattern: str) -> np.ndarray:
        """Match result per distinct value of ``column``; an invalid regex matches nothing."""
        key = (column, pattern)
        found = self._cache.get(key)
        if found is None:
            texts = self._texts[column]
            try:
                found = texts.search(pattern)
            except re.error as e:
                logger.error("invalid regex %r: %s", pattern, e)
                found = np.zeros(len(texts.values), dtype=bool)
            if len(self._cache) >= self.CACHE_LIMIT:
                self._cache.clear()
            self._cache[key] = found
        return found

    def mask(self, tagger: Tagger) -> np.ndarray:
        """Boolean array over the rows matched by ``tagger`` (both regexes; an empty regex matches everything)."""
        mask = None
        for column, pattern in ((Col.recipient, tagger.regex_recipient), (Col.description, tagger.regex_description)):
            if pattern:
                rows = self.distinct_matches(column, pattern)[self._texts[column].codes]
                mask = rows if mask is None else mask & rows
        return np.ones(self.size, dtype=bool) if mask is None else mask


def apply_taggers(
    transactions: pd.DataFrame,
    taggers: Iterable[Tagger],
    one_time_tags: Mapping[str, OneTimeTag] | None = None,
    matcher: TagMatcher | None = None,
) -> pd.DataFrame:
    """Return a copy of ``transactions`` with ``tag``, ``tagger_name`` and ``recurring`` columns.

    Taggers are applied in order; a later tagger overwrites an earlier one. One-time tags win over all taggers.
    Pass a :class:`TagMatcher` built from the same ``transactions`` to reuse its cached regex results.
    """
    taggers = list(taggers)
    if matcher is None:
        matcher = TagMatcher(transactions)
    if matcher.size != len(transactions):
        raise ValueError("the matcher was built for other transactions")
    winner = np.full(len(transactions), -1, dtype=np.int64)
    for i, tagger in enumerate(taggers):
        winner[matcher.mask(tagger)] = i
    # index -1 (no tagger) picks the last element: untagged
    tags = np.array([t.tag for t in taggers] + [UNTAGGED], dtype=object)
    names = np.array([t.name for t in taggers] + [""], dtype=object)
    recurring = np.array([recurring_to_float(t.recurring) for t in taggers] + [np.nan], dtype=float)

    df = transactions.copy()
    df[Col.tag] = tags[winner]
    df[Col.tagger_name] = names[winner]
    df[Col.recurring] = recurring[winner]
    if one_time_tags:
        overrides = df[Col.transaction_id].map(one_time_tags)
        mask = overrides.notna().to_numpy()
        if mask.any():
            chosen = overrides[mask]
            df.loc[mask, Col.tag] = [t.tag for t in chosen]
            df.loc[mask, Col.tagger_name] = ONE_TIME_TAGGER
            df.loc[mask, Col.recurring] = [recurring_to_float(t.recurring) for t in chosen]
    for column in (Col.tag, Col.tagger_name):
        df[column] = df[column].astype(str)
    return df
