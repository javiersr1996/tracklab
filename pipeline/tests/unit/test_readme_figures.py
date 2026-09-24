"""Every figure in the README prose is one a built artefact holds (task 24).

A figure is a number outside code blocks, inline code and links; it must appear
in `web/public/data/stats.json` or among the numbers of `pipeline/reports/`.
Thousands separators are the README's own formatting and are dropped first.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PIPELINE = Path(__file__).resolve().parents[2]
REPO = PIPELINE.parent
NUMBER = re.compile(r"(?<![\w.-])\d[\d,]*(?:\.\d+)?(?![\w-])")


def readme_figures(text: str) -> list[str]:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"https?://\S+", "", text)
    return [m.group().rstrip(",").replace(",", "") for m in NUMBER.finditer(text)]


def _numbers(value: Any) -> set[str]:
    if isinstance(value, bool):
        return set()
    if isinstance(value, int | float):
        return {str(value)}
    if isinstance(value, dict):
        return set().union(*(_numbers(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_numbers(v) for v in value))
    return set()


def artefact_numbers() -> set[str]:
    stats = json.loads((REPO / "web" / "public" / "data" / "stats.json").read_text("utf-8"))
    found = _numbers(stats)
    for report in (PIPELINE / "reports").iterdir():
        found |= set(re.findall(r"\d+(?:\.\d+)?", report.read_text("utf-8")))
    return found


def test_readme_figures_come_from_artefacts() -> None:
    figures = readme_figures((REPO / "README.md").read_text("utf-8"))
    print(f"README figures: {figures}")
    assert figures, "the README quotes no figure at all: the regex is broken"
    assert [f for f in figures if f not in artefact_numbers()] == []


def test_a_typed_figure_is_caught() -> None:
    assert readme_figures("rows: 9,126,745 in `frames` and 12 in ```x 99```") == [
        "9126745",
        "12",
    ]
    assert "9126745" not in artefact_numbers()
