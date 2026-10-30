"""Large synthetic data set for performance tests (all made up, deterministic).

Sized above a typical household over many years: several accounts, ~5 transactions per day, mostly unique
purposes (reference numbers, time stamps), hundreds of rules created by double click and by hand.
"""

from __future__ import annotations

import random
import re

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain.categorization import regex_for
from mymoneyvisualizer.domain.columns import Col, new_transaction_ids, normalize_transactions
from mymoneyvisualizer.domain.models import (
    GROUP_INCOME,
    GROUP_NEEDS,
    GROUP_WANTS,
    GroupAssignment,
    ManualCategory,
    Rule,
    Settings,
)
from mymoneyvisualizer.storage.repository import State

#: (merchant, main category, subcategory, typical amount, monthly frequency per account)
MERCHANTS = [
    ("REWE Markt", "household", "food", -45, 6),
    ("EDEKA Center", "household", "food", -38, 4),
    ("ALDI SÜD", "household", "food", -31, 4),
    ("Lidl sagt Danke", "household", "food", -27, 3),
    ("PENNY Markt", "household", "food", -19, 2),
    ("Bäckerei Müller", "household", "bakery", -6, 8),
    ("dm-drogerie markt", "household", "drugstore", -17, 2),
    ("Rossmann", "household", "drugstore", -14, 1),
    ("Shell", "car", "fuel", -62, 2),
    ("ARAL Station", "car", "fuel", -58, 1),
    ("DB Fernverkehr AG", "mobility", "train", -79, 0.3),
    ("MVG Muenchen", "mobility", "public", -3.5, 4),
    ("Amazon EU S.a.r.l.", "shopping", "online", -37, 3),
    ("Zalando SE", "shopping", "clothes", -64, 0.5),
    ("IKEA Deutschland", "shopping", "home", -89, 0.2),
    ("OBI Markt", "shopping", "diy", -42, 0.4),
    ("Netflix International B.V.", "leisure", "streaming", -13.99, 1),
    ("Spotify AB", "leisure", "music", -10.99, 1),
    ("Cinemaxx", "leisure", "cinema", -24, 0.3),
    ("Restaurant Da Vinci", "leisure", "restaurant", -48, 1),
    ("Lieferando.de", "leisure", "food delivery", -27, 1),
    ("Apotheke am Markt", "health", "pharmacy", -18, 0.6),
    ("Zahnarztpraxis Dr. Weiß", "health", "dentist", -65, 0.1),
    ("Fitnessstudio Sportwerk", "leisure", "sport", -39.9, 1),
]
#: monthly fixed items: (recipient, purpose, main category, subcategory, amount)
FIXED = [
    ("Musterfirma GmbH", "Gehalt {m:02d}/{y} PersNr 4711", "income", "salary", 3245.67),
    ("Hausverwaltung Schröder & Söhne", "Miete {mon} {y} Whg. 3 OG links", "housing", "rent", -1050.0),
    ("Stadtwerke Bühl GmbH", "Abschlag Strom {mon} {y} Vertragskonto 4711-0815", "housing", "power", -78.0),
    ("Telekom Deutschland GmbH", "Festnetz/DSL Rechnung {m:02d}/{y} Kundennr. 0815", "housing", "internet", -39.95),
    ("HUK-COBURG", "Kfz-Versicherung Beitrag {m:02d}/{y}", "insurance", "car", -41.2),
]
MONTHS = [
    "Januar",
    "Februar",
    "Maerz",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


def _transactions(rng: random.Random, account: int, start: pd.Period, months: int, per_month: float) -> pd.DataFrame:
    rows = []
    for offset in range(months):
        month = start + offset
        y, m = month.year, month.month
        days = month.days_in_month
        if account == 0:
            for recipient, purpose, *_rest, amount in FIXED:
                rows.append(
                    (
                        pd.Timestamp(y, m, rng.randint(1, 5)),
                        recipient,
                        purpose.format(m=m, y=y, mon=MONTHS[m - 1]),
                        amount,
                    )
                )
            rows.append((pd.Timestamp(y, m, 20), "Max Mustermann", f"Sparen {MONTHS[m - 1]} {y}", -400.0))
        if account == 1:
            rows.append((pd.Timestamp(y, m, 21), "Max Mustermann", f"Sparen {MONTHS[m - 1]} {y}", 400.0))
        for merchant, _base, _sub, amount, frequency in MERCHANTS:
            count = int(frequency * per_month) + (1 if rng.random() < (frequency * per_month) % 1 else 0)
            for _ in range(count):
                day = rng.randint(1, days)
                branch = rng.randint(1, 120)
                stamp = f"{y}-{m:02d}-{day:02d}T{rng.randint(7, 21):02d}:{rng.randint(0, 59):02d}"
                reference = rng.randint(10**7, 10**8 - 1)
                purpose = f"{merchant.upper()} SAGT DANKE {reference}//{stamp} Folgenr. 00{rng.randint(1, 9)}"
                value = round(amount * rng.uniform(0.4, 1.8), 2)
                rows.append((pd.Timestamp(y, m, day), f"{merchant} {branch}", purpose, value))
    df = pd.DataFrame(rows, columns=[Col.date, Col.recipient, Col.description, Col.value])
    df[Col.transaction_id] = new_transaction_ids(len(df))
    return normalize_transactions(df.sort_values(Col.date, ascending=False, kind="stable"))


def build_state(
    accounts: int = 8, years: int = 12, per_month: float = 1.5, rules: int = 700, manual: int = 400, seed: int = 7
) -> State:
    rng = random.Random(seed)
    start = pd.Period("2014-11", "M")
    names = ["Girokonto", "Tagesgeld", *[f"Konto {i}" for i in range(2, accounts)]]
    state = State(settings=Settings(budget_period="2025"))
    for i, name in enumerate(names):
        state.accounts[name] = _transactions(rng, i, start, years * 12, per_month * (1.0 if i < 2 else 0.6))
    combined = pd.concat(state.accounts.values(), ignore_index=True)

    rule_list: list[Rule] = []
    for recipient, _purpose, base, sub, _amount in FIXED:
        rule_list.append(Rule(category=f"{base}.{sub}", regex_recipient=re.escape(recipient)))
    rule_list.append(Rule(category="Tagesgeld", regex_description="^Sparen ", regex_recipient="Max"))
    rule_list.append(Rule(category="Girokonto", regex_description="^Sparen ", regex_recipient="Max"))
    kinds = ["merchant", "double click", "description", "alternation", "regex"]
    weights = [30, 40, 12, 12, 6]
    while len(rule_list) < rules:
        kind = rng.choices(kinds, weights)[0]
        merchant, base, sub, *_ = rng.choice(MERCHANTS)
        category = f"{base}.{sub}" if rng.random() < 0.8 else f"{base}.{sub}.{rng.randint(1, 5)}"
        if kind == "merchant":
            rule = Rule(category=category, regex_recipient=f"{re.escape(merchant)} {rng.randint(1, 120)}$")
        elif kind == "double click":
            row = combined.iloc[rng.randrange(len(combined))]
            rule = Rule(
                category=category,
                regex_recipient=regex_for(row[Col.recipient]),
                regex_description=regex_for(row[Col.description]),
            )
        elif kind == "description":
            rule = Rule(category=category, regex_description=re.escape(merchant.upper()))
        elif kind == "alternation":
            others = rng.sample(MERCHANTS, 3)
            rule = Rule(category=category, regex_recipient="|".join(re.escape(o[0]) for o in others))
        else:
            rule = Rule(category=category, regex_description=rf"^{re.escape(merchant.upper()[:4])}.* \d{{8}}//20\d\d-")
        rule_list.append(rule)
    state.rules = rule_list

    ids = combined[Col.transaction_id].to_numpy()
    for i, transaction_id in enumerate(np.random.default_rng(seed).choice(ids, size=manual, replace=False)):
        # every tenth one is a durable purchase, spread over five years with a residual value
        spread = (60, 30) if i % 10 == 0 else (0, 0)
        state.manual_categories[str(transaction_id)] = ManualCategory(str(transaction_id), "leisure.gift", *spread)
    bases = sorted({t.category.split(".")[0] for t in rule_list} | {"leisure"})
    state.groups = [
        GroupAssignment(
            b,
            GROUP_INCOME if b == "income" else GROUP_WANTS if b in ("leisure", "shopping") else GROUP_NEEDS,
        )
        for b in bases
        if b not in state.accounts
    ]
    return state
