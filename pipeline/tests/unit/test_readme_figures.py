"""Every figure in the README prose is one a built artefact holds (task 24).

A figure is a number outside code blocks, inline code and links; it must appear
in `web/public/data/stats.json`, the file the README names as its only source.
Any number of `pipeline/reports/` would be too loose: with every integer found
there, a small invented figure would pass (final review, row V). Thousands
separators are the README's own formatting and are dropped first.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
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


DATA_DIR = REPO / "web" / "public" / "data"


def artefact_numbers() -> set[str]:
    """The numbers of stats.json, plus each table's rows per sport summed over its
    matches (the figure the site shows, `rowsOf` in web/lib/data.ts), plus
    every number platform.json, lineage.json and the three warehouse files carry
    (task 34: the measured title and the graph's own counts; task 46: the
    Warehouse section)."""
    stats = json.loads((DATA_DIR / "stats.json").read_text("utf-8"))
    per_sport: dict[tuple[str, str], int] = {}
    for row in stats["tables"]:
        key = (row["table"], row["sport"])
        per_sport[key] = per_sport.get(key, 0) + row["rows"]
    numbers = _numbers(stats) | {str(n) for n in per_sport.values()}
    for name in (
        "platform.json",
        "lineage.json",
        "warehouse.json",
        "warehouse_examples.json",
        "warehouse_pg.json",
    ):
        path = DATA_DIR / name
        if path.is_file():
            numbers |= _numbers(json.loads(path.read_text("utf-8")))
    return numbers


def test_readme_figures_come_from_artefacts() -> None:
    figures = readme_figures((REPO / "README.md").read_text("utf-8"))
    print(f"README figures: {figures}")
    assert figures, "the README quotes no figure at all: the regex is broken"
    assert [f for f in figures if f not in artefact_numbers()] == []


def test_a_typed_figure_is_caught() -> None:
    assert readme_figures("rows: 9,126,745 in `frames` and 7654321 in ```x 99```") == [
        "9126745",
        "7654321",
    ]
    assert "9126745" not in artefact_numbers()
    assert "7654321" not in artefact_numbers()


def _readme_title_and_subtitle(readme: str) -> tuple[str | None, str | None]:
    title = re.search(r"^title: (.+)$", readme, flags=re.M)
    subtitle = re.search(r"^subtitle: (.+)$", readme, flags=re.M)
    return (title.group(1) if title else None, subtitle.group(1) if subtitle else None)


def test_readme_title_and_asset_count_are_the_artefacts() -> None:
    """The figures the README quotes inside code, where the test above cannot see
    them: the title and subtitle `tracklab publish platform` prints and the asset count."""
    readme = (REPO / "README.md").read_text("utf-8")
    platform = json.loads((DATA_DIR / "platform.json").read_text("utf-8"))
    lineage = json.loads((DATA_DIR / "lineage.json").read_text("utf-8"))
    assets = re.search(r"lists `(\d+)` assets", readme)
    assert assets, "the README no longer quotes the asset count"
    assert _readme_title_and_subtitle(readme) == (platform["title"], platform["subtitle"])
    assert int(assets.group(1)) == sum(1 for n in lineage["nodes"] if n["kind"] == "asset")


def test_a_typed_subtitle_is_caught() -> None:
    """A subtitle typed with a different figure must not equal the artefact's."""
    platform = json.loads((DATA_DIR / "platform.json").read_text("utf-8"))
    typed = "subtitle: 9.9 MB to watch, 0.1 MB to query"
    readme = "title: " + platform["title"] + chr(10) + typed + chr(10)
    assert _readme_title_and_subtitle(readme) != (platform["title"], platform["subtitle"])
    assert _readme_title_and_subtitle("no lines") == (None, None)
