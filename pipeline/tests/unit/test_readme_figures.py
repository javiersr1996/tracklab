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


def _frames(stats: Any, sport: str) -> int:
    return sum(r["rows"] for r in stats["tables"] if r["table"] == "frames" and r["sport"] == sport)


def prose_expected() -> list[str]:
    """The sentences of the prose that carry a figure, each with the number read from the field it
    stands for: `frames` per sport (the figure the site shows, `rowsOf` in web/lib/data.ts, so
    summed over the matches) and the bytes of stats.json. A figure that is in stats.json under
    another field is wrong (review V of P4, B10: the two `frames` figures swapped passed)."""
    stats = _artefact("stats.json")
    basketball, football = _frames(stats, "basketball"), _frames(stats, "football")
    raw, published = stats["bytes"]["raw"]["total"], stats["bytes"]["published"]["total"]
    return [
        f"returns {basketball:,} rows of basketball and {football:,} of football",
        f"weigh {raw:,} bytes as pinned (`bytes.raw.total`)",
        f"the site ships {published:,} bytes of possessions (`bytes.published.total`)",
    ]


def prose_problems(readme: str) -> list[str]:
    """`prose_expected` missing from the README, and any other figure in its prose."""
    flat = " ".join(readme.split())
    expected = prose_expected()
    allowed = {n.replace(",", "") for n in NUMBER.findall(" ".join(expected))}
    return [f"not in the README: {e!r}" for e in expected if e not in flat] + [
        f"in the prose, from no field: {f}" for f in readme_figures(readme) if f not in allowed
    ]


def test_readme_figures_come_from_artefacts() -> None:
    readme = README.read_text("utf-8")
    print(f"README figures: {readme_figures(readme)}")
    assert readme_figures(readme), "the README quotes no figure at all: the regex is broken"
    assert prose_problems(readme) == []


def test_a_typed_figure_is_caught() -> None:
    assert readme_figures("rows: 9,126,745 in `frames` and 12 in ```x 99```") == [
        "9126745",
        "12",
    ]
    flat = " ".join(README.read_text("utf-8").split())
    assert prose_problems(flat.replace("9,126,744", "9,126,745")) != []


def test_a_figure_of_another_field_is_caught() -> None:
    """The real README with the figures swapped for others that stats.json does hold: the two
    `frames` figures, and the published bytes of football in place of the total."""
    stats = _artefact("stats.json")
    flat = " ".join(README.read_text("utf-8").split())
    basketball, football = (f"{_frames(stats, sport):,}" for sport in ("basketball", "football"))
    published = f"{stats['bytes']['published']['total']:,}"
    swapped = flat.replace(basketball, "@").replace(football, basketball).replace("@", football)
    other_bytes = flat.replace(published, f"{stats['bytes']['published']['football']:,}")
    for text in (swapped, other_bytes):
        assert text != flat, "the mutation changed nothing: the README moved on, update this test"
        assert prose_problems(text) != []


# The only numbers in code that are not measurements: the second load's contract and the exit code
# of `ingest`. Exact phrases, so a stray `0` or `1` elsewhere in code is a problem (review V of P4,
# B10).
NOT_FIGURES = ("`inserted=0 updated=0 deleted=0`", "Exit code `1`")


def code_figures(text: str) -> list[str]:
    """The numbers `readme_figures` leaves out: those in code blocks and in inline code."""
    for phrase in NOT_FIGURES:
        text = text.replace(phrase, "")
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
    # The sentences out first: a number elsewhere in code is no figure of theirs, even when it
    # equals one (`76` ms or `2.3` s passed while the allowed set held every number of the five).
    rest = flat
    for sentence in expected:
        rest = rest.replace(sentence, "")
    return problems + [f"in code, from no artefact: {n}" for n in code_figures(rest)]


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
    # A number that equals one of the figures, or a 0 or a 1, in a place that is none of theirs.
    for stray in ("76", "2.3", "0", "1"):
        mutated.append(flat.replace("## Warehouse ", f"## Warehouse It answers in `{stray}` s. "))
    assert len(mutated) == 15
    for text in mutated:
        assert text != flat, "the mutation changed nothing: the README moved on, update this test"
        assert code_problems(text) != []
