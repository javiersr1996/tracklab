"""Every figure in the README prose is one a built artefact holds (task 24).

A figure is a number outside code blocks, inline code and links; it must appear
in `web/public/data/stats.json`, the file the README names as its only source.
Any number of `pipeline/reports/` would be too loose: with every integer found
there, a small invented figure would pass (final review, row V). Thousands
separators are the README's own formatting and are dropped first.

A figure inside code is checked against the one field it stands for
(`code_problems`), and a number in code that stands for none fails (review V
of P4, M2: the Warehouse section quoted four, and no test read them).
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
README = REPO / "README.md"


def _artefact(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text("utf-8"))


def artefact_numbers() -> set[str]:
    """The numbers of stats.json, plus each table's rows per sport summed over its matches (the
    figure the site shows, `rowsOf` in web/lib/data.ts). Nothing else: the prose names stats.json
    as its source and quotes four of these, and every other file let in here admits all its
    numbers to the prose (task 46 had added platform, lineage and the three warehouse files: 727
    numbers admitted instead of 391, review V of P4, M2). The figures in code are read field by
    field in `code_problems`."""
    stats = _artefact("stats.json")
    per_sport: dict[tuple[str, str], int] = {}
    for row in stats["tables"]:
        key = (row["table"], row["sport"])
        per_sport[key] = per_sport.get(key, 0) + row["rows"]
    return _numbers(stats) | {str(n) for n in per_sport.values()}


def test_readme_figures_come_from_artefacts() -> None:
    figures = readme_figures(README.read_text("utf-8"))
    print(f"README figures: {figures}")
    assert figures, "the README quotes no figure at all: the regex is broken"
    assert [f for f in figures if f not in artefact_numbers()] == []


def test_a_typed_figure_is_caught() -> None:
    assert readme_figures("rows: 9,126,745 in `frames` and 12 in ```x 99```") == [
        "9126745",
        "12",
    ]
    assert "9126745" not in artefact_numbers()
    assert "12" not in artefact_numbers()


# Numbers in code that are not measurements: the second load's contract (`inserted=0 updated=0
# deleted=0`) and the exit code of `ingest`.
NOT_FIGURES = frozenset({"0", "1"})


def code_figures(text: str) -> list[str]:
    """The numbers `readme_figures` leaves out: those in code blocks and in inline code."""
    blocks = re.findall(r"```.*?```", text, flags=re.S)
    inline = re.findall(r"`[^`]*`", re.sub(r"```.*?```", "", text, flags=re.S))
    return [m.group().replace(",", "") for s in blocks + inline for m in NUMBER.finditer(s)]


def code_expected() -> list[str]:
    """What the README must say in code, read from the field each figure stands for: the title
    and subtitle `tracklab publish platform` prints (platform.json), the asset count
    (lineage.json), the long fact's rows and row group size (warehouse.json), and the Postgres
    database's bytes and fact rows (warehouse_pg.json)."""
    platform, lineage = _artefact("platform.json"), _artefact("lineage.json")
    warehouse, pg = _artefact("warehouse.json"), _artefact("warehouse_pg.json")
    fact = next(t for t in warehouse["tables"] if t["table"] == "fact")
    group = max(g["rows"] for g in fact["row_groups"])
    pg_fact = next(t for t in pg["tables"] if t["table"] == "fact_player_season_metric")
    assets = sum(1 for n in lineage["nodes"] if n["kind"] == "asset")
    return [
        f"title: {platform['title']}",
        f"subtitle: {platform['subtitle']}",
        f"lists `{assets}` assets",
        f"has `{fact['rows']}` rows in row groups of `{group}` ordered by metric",
        f"`{pg['database_bytes']}` bytes for the whole database, `{pg_fact['rows']}` rows in the "
        "fact table",
    ]


def code_problems(readme: str) -> list[str]:
    """`code_expected` missing from the README, the Postgres numbers said to come from Docker
    when warehouse_pg.json says otherwise (or the reverse), and any other number in code."""
    flat = " ".join(readme.split())
    expected = code_expected()
    problems = [f"not in the README: {e!r}" for e in expected if e not in flat]
    where = _artefact("warehouse_pg.json")["source"]["where_id"]
    if ("a local Postgres in Docker" in flat) != (where == "local"):
        problems.append(f"where the Postgres numbers come from: {where}")
    allowed = set(NUMBER.findall(" ".join(expected))) | NOT_FIGURES
    return problems + [
        f"in code, from no artefact: {n}" for n in code_figures(readme) if n not in allowed
    ]


def test_readme_figures_in_code_are_the_artefacts() -> None:
    """The figures inside code, where `test_readme_figures_come_from_artefacts` cannot see them."""
    readme = README.read_text("utf-8")
    print(f"README figures in code: {code_figures(readme)}")
    assert code_problems(readme) == []


def _another(number: str) -> str:
    return number[:-1] + str((int(number[-1]) + 1) % 10)


def test_a_changed_figure_in_code_is_caught() -> None:
    """The real README with each figure in code changed, one at a time, plus a sentence that
    moves the Postgres numbers to Neon and a new figure in code: each must be a problem (the
    typed subtitle of task 46 only tested the helper, review V of P4, B8)."""
    flat = " ".join(README.read_text("utf-8").split())
    mutated = [
        flat.replace(sentence, sentence[: m.start()] + _another(m.group()) + sentence[m.end() :])
        for sentence in code_expected()
        for m in NUMBER.finditer(sentence)
    ]
    mutated.append(flat.replace("a local Postgres in Docker", "Neon"))
    mutated.append(flat.replace("## Warehouse ", "## Warehouse It answers in `250` ms. "))
    assert len(mutated) == 11
    for text in mutated:
        assert text != flat, "the mutation changed nothing: the README moved on, update this test"
        assert code_problems(text) != []
