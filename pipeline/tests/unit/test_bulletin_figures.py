"""Every figure in `docs/bulletin.md` prose is one already in `reports/quality_*.csv`
or in `web/public/data/quality.json` (task 30), the same idea as
`test_readme_figures.py`: a figure is a number outside code blocks, inline code
and links. The two artefacts' numbers are pooled with their sign dropped, because
the figure regex below (shared with the README's) never keeps a leading `-`, so
a bulletin phrase like "14.7 to 19.3% below standard" reads as `14.7` and `19.3`.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from tracklab.quality.common import report_path
from tracklab.quality.run import CHECKS

REPO = Path(__file__).resolve().parents[3]
PIPELINE = REPO / "pipeline"
REPORTS = PIPELINE / "reports"
QUALITY_JSON = REPO / "web" / "public" / "data" / "quality.json"
BULLETIN = REPO / "docs" / "bulletin.md"

NUMBER = re.compile(r"(?<![\w.-])\d[\d,]*(?:\.\d+)?(?![\w-])")


def bulletin_figures(text: str) -> list[str]:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"https?://\S+", "", text)
    return [m.group().rstrip(",").replace(",", "") for m in NUMBER.finditer(text)]


def _json_numbers(value: Any) -> set[str]:
    if isinstance(value, bool):
        return set()
    if isinstance(value, int | float):
        return {str(abs(value))}
    if isinstance(value, dict):
        out: set[str] = set()
        for v in value.values():
            out |= _json_numbers(v)
        return out
    if isinstance(value, list):
        out = set()
        for v in value:
            out |= _json_numbers(v)
        return out
    return set()


def _csv_numbers() -> set[str]:
    numbers: set[str] = set()
    for check in CHECKS:
        with report_path(REPORTS, check).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                numbers.add(row["value"].lstrip("-"))
                numbers.add(row["n"])
    return numbers


def artefact_numbers() -> set[str]:
    """Every number of the six quality reports and of `quality.json`, magnitude
    only: the only two sources the bulletin is allowed to quote a figure from."""
    payload = json.loads(QUALITY_JSON.read_text("utf-8"))
    return _csv_numbers() | _json_numbers(payload)


def quoted(figure: str, numbers: set[str]) -> bool:
    """A figure is quoted if an artefact holds it, or holds a value that rounds to
    it at the figure's own decimals: the bulletin rounds for reading, the CSV keeps
    the full value."""
    if figure in numbers:
        return True
    digits = len(figure.split(".")[1]) if "." in figure else 0
    target = float(figure)
    return any(abs(round(float(n), digits) - target) < 1e-9 for n in numbers)


def test_bulletin_figures_come_from_artefacts() -> None:
    figures = bulletin_figures(BULLETIN.read_text("utf-8"))
    print(f"bulletin figures: {figures}")
    assert figures, "the bulletin quotes no figure at all: the regex is broken"
    numbers = artefact_numbers()
    assert [f for f in figures if not quoted(f, numbers)] == []


def test_a_typed_figure_is_caught() -> None:
    assert bulletin_figures("gap 14.7318% and `9999` at http://example.com/999") == ["14.7318"]
    assert not quoted("424242", artefact_numbers())
    assert quoted("14.7", {"14.7255"}) and not quoted("14.8", {"14.7255"})
