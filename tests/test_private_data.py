"""The repository is public: no real account numbers in code or test data.

Every IBAN-like text with a valid checksum must be one of the documented example IBANs. Made-up test IBANs have
invalid checksums. The failure message masks the number, so a real IBAN does not end up in public CI logs either.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCANNED = [ROOT / "README.md", ROOT / "mymoneyvisualizer", ROOT / "tests"]
#: example IBANs from public documentation (Wikipedia, bank manuals)
EXAMPLES = {"DE89370400440532013000", "DE02120300000000202051"}
IBAN = re.compile(r"\b[A-Z]{2}[0-9]{2}(?: ?[0-9A-Z]{4}){3,7}(?: ?[0-9A-Z]{1,4})?\b")


def is_valid_iban(text: str) -> bool:
    """ISO 13616 checksum: the rearranged number taken modulo 97 is 1."""
    rearranged = text[4:] + text[:4]
    return int("".join(str(int(char, 36)) for char in rearranged)) % 97 == 1


def _text(path: Path) -> str:
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    return data.decode("latin-1")


def _files():
    for entry in SCANNED:
        paths = [entry] if entry.is_file() else entry.rglob("*")
        yield from (p for p in paths if p.is_file() and "__pycache__" not in p.parts)


def test_checksum():
    assert is_valid_iban("DE89370400440532013000")
    assert not is_valid_iban("DE12345678901234567890")


def test_no_real_ibans_in_the_repository():
    found = []
    for path in _files():
        for match in IBAN.finditer(_text(path)):
            iban = match.group().replace(" ", "")
            if iban not in EXAMPLES and is_valid_iban(iban):
                found.append(f"{path.relative_to(ROOT)}: {iban[:4]}…{iban[-2:]}")
    assert not found, "valid IBANs found, real account numbers must not be committed:\n" + "\n".join(found)
