"""`tracklab learn gravity`: the SQL of "Reproduce it", run on the public bundle (task 76).

`gravity.sql` is the one source: the page shows it and this module runs it, match by match,
changing only the match id in its two file names. It is P3's basketball check
(`quality/gravity.py`) in DuckDB: shots with a `startFrame` that are not blocked; the apex is the
highest ball sample from 10 frames before `startFrame` to 19 after the end (`startFrame` + 25
without one), the first on a tie; the window is the apex +-10 frames, all present; after the apex
the ball may not come within 2.5 ft of a rim axis or below 9.5 ft; the fit's residual RMS is
under 1 ft; g is the exact `median`, never `approx_quantile`. The fit is the closed form of a
window symmetric in time.

`--check` compares `flights` and `g_median` of every basketball match of `quality.json` with what
the SQL gives on the raw files: `FULL n/n` if all n were recomputed. Without the bundle it says
`PARTIAL k/n` and what it checked instead: that the SQL names its match id exactly twice and that
the file holds the n matches it would be compared with.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb

from tracklab.bronze.common import raw_root_for

SOURCE_ID = "opendata-basketball"
SQL_PATH = Path(__file__).with_name("gravity.sql")
SQL_MATCH_ID = "114086"  # the id the public SQL is written for
G_TOLERANCE = 5e-5  # both g are rounded to 4 decimals

Figures = tuple[int, float | None]  # (flights, g_median)


def read_sql() -> str:
    return SQL_PATH.read_bytes().decode("utf-8")


def match_sql(match_id: int) -> str:
    return read_sql().replace(SQL_MATCH_ID, str(match_id))


def run_sql(sql: str, match_dir: Path) -> Figures:
    """The SQL run from `match_dir`, where its two file names are relative."""
    here = Path.cwd()
    os.chdir(match_dir)
    try:
        con = duckdb.connect()
        con.execute("SET enable_progress_bar = false")
        row = con.execute(sql).fetchone()
    finally:
        os.chdir(here)
    assert row is not None
    return int(row[0]), None if row[1] is None else float(row[1])


def published(quality: Path) -> dict[int, Figures]:
    """Basketball native match id -> (flights, g_median) as quality.json publishes them."""
    rows = json.loads(quality.read_text(encoding="utf-8"))["checks"]["gravity"]
    flights: dict[int, int] = {}
    medians: dict[int, float] = {}
    for r in rows:
        if r["sport"] != "basketball":
            continue
        native = int(r["match_id"].removeprefix("bb:"))
        if r["metric"] == "flights":
            flights[native] = int(r["value"])
        elif r["metric"] == "g_median":
            medians[native] = float(r["value"])
    return {native: (n, medians.get(native)) for native, n in flights.items()}


def _equal(got: Figures, want: Figures) -> bool:
    if got[0] != want[0]:
        return False
    if got[1] is None or want[1] is None:
        return got[1] is None and want[1] is None
    return abs(got[1] - want[1]) < G_TOLERANCE


def run_learn_gravity(data_dir: Path, quality: Path, *, check: bool = False) -> int:
    want = published(quality)
    named = read_sql().count(SQL_MATCH_ID)
    if named != 2:
        print(f"learn gravity: gravity.sql names {SQL_MATCH_ID} {named} times, not 2")
        return 1
    try:
        matches = raw_root_for(data_dir, SOURCE_ID) / "data" / "matches"
    except (FileNotFoundError, RuntimeError):
        matches = None
    different: list[int] = []
    done = 0
    for match_id, figures in sorted(want.items()):
        if matches is None or not (matches / str(match_id)).is_dir():
            continue
        got = run_sql(match_sql(match_id), matches / str(match_id))
        done += 1
        same = _equal(got, figures)
        print(
            f"learn gravity {match_id}: flights={got[0]} g_median={got[1]} "
            f"(quality.json: {figures[0]}, {figures[1]}) {'equal' if same else 'DIFFERENT'}"
        )
        if not same:
            different.append(match_id)
    total = len(want)
    if different:
        print(f"learn gravity: {different} differ from {quality.name}")
        return 1
    if done == total:
        if check:
            print(f"learn gravity --check: FULL {done}/{total}: flights and g_median equal")
        return 0
    if not check:
        print(f"learn gravity: the raw files of {total - done} of {total} matches are not at hand")
        return 1
    print(
        f"learn gravity --check: PARTIAL {done}/{total}: raw files not at hand for the rest; "
        f"the SQL names its match id twice and {quality.name} holds {total} matches to compare with"
    )
    return 0
