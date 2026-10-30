"""Regression: setup.py only listed the top level package, so ``pip install .`` missed all sub packages."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_every_source_directory_is_a_package():
    """``packages.find`` only discovers directories with an ``__init__.py``."""
    source_dirs = {p.parent for p in (ROOT / "mymoneyvisualizer").rglob("*.py") if "__pycache__" not in p.parts}
    missing = [d.relative_to(ROOT) for d in source_dirs if not (d / "__init__.py").is_file()]
    assert missing == []


def test_pyproject_discovers_packages_automatically():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    setuptools = config["tool"]["setuptools"]
    assert "packages" not in config["project"]
    assert setuptools["packages"]["find"]["include"] == ["mymoneyvisualizer*"]
    assert config["project"]["scripts"]["mmv"] == "mymoneyvisualizer.cli:main"
