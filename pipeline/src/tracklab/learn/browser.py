"""`tracklab learn browser`: the queries of "Run it here", run on the published files (task 86).

Each lesson of P8 has a `<slug>.browser.sql`: a `-- files:` line with the files under
`web/public/data` it reads (by their path on the site, `/data/...`), the `CREATE VIEW` statements
that flatten them, and one query whose rows are `(figure, value)`: the name of a `data-fig` the
lesson prints and the value the query computes for it. The page reads the same file at build time:
it registers the files, creates the views and puts the query in the box, and the browser compares
each row with the figure of that name (`matched k of n`, e2e/learn-reproduce.spec.ts).

This module runs the same statements with DuckDB on `web/public/data`, the `/data/` paths pointed
at that folder, and compares the rows it can with the files themselves: a figure the files carry
(a sample rate, a range of medians) is compared exactly, and a figure only the lesson's TypeScript
prints is compared, where the files have its counterpart, with that counterpart (the hook's g with
P3's `g_data` within the rounding of its 21 samples; the arrival times with the published ones).
The rest is the e2e's. `--check` says `FULL k/k` when every lesson ran, read only its declared
files, and had at least one row compared, all equal.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

LESSONS = ("gravity", "speed", "coordinates", "rebound", "cadence", "clock")
HERE = Path(__file__).parent
FILES_LINE = re.compile(r"^-- files: (.+)$", re.MULTILINE)
VIEW = re.compile(r"^CREATE VIEW (\w+) AS", re.MULTILINE)
READS = re.compile(r"read_json\('(/data/[^']+)'")

# The hook's g from its 21 published samples against P3's `g_data`, from the unrounded z: the
# bound of a 0.05 mm rounding on the closed form (lesson 1's `rounding_bound`, 0.00164 m/s²) plus
# half a unit of `g_data`'s last decimal, as in web/tests/learn-gravity.test.ts.
HOOK_G_TOLERANCE = 0.00164 + 0.00005
# The cadence of the hook window from its samples in mm against P6's, from the joints at full
# precision: the window's own rounding moves it in the fifth decimal (measured: 5e-5 Hz).
CADENCE_TOLERANCE = 0.0005


@dataclass(frozen=True)
class BrowserSql:
    files: list[str]
    views: list[str]  # each a CREATE VIEW statement, comments included
    query: str


def parse(text: str) -> BrowserSql:
    """The `-- files:` line, the views and the query of a `.browser.sql`, split on `;` at a line
    end: every statement but the last is a CREATE VIEW, the last is the query."""
    files = FILES_LINE.search(text)
    if files is None:
        raise ValueError("no `-- files:` line")
    statements = [s.strip() for s in re.split(r";[ \t]*\n", text) if s.strip()]
    *views, query = statements
    if not views or any(VIEW.search(v) is None for v in views) or VIEW.search(query):
        raise ValueError("the statements are not views followed by one query")
    return BrowserSql(files.group(1).split(), views, query.rstrip(";").rstrip())


def read(slug: str) -> BrowserSql:
    return parse((HERE / f"{slug}.browser.sql").read_bytes().decode("utf-8"))


def undeclared(sql: BrowserSql) -> list[str]:
    """Paths a view reads that its `-- files:` line does not declare: the browser registers only
    the declared ones, so such a view fails there (`allowed_paths`)."""
    return sorted({p for v in sql.views for p in READS.findall(v)} - set(sql.files))


def run(sql: BrowserSql, public: Path) -> dict[str, str]:
    """The query's rows, figure -> value, with every `/data/` path under `public`."""
    root = public.resolve().as_posix()

    def local(statement: str) -> str:
        return statement.replace("'/data/", f"'{root}/data/")

    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    for v in sql.views:
        con.execute(local(v))
    rows = con.execute(local(sql.query)).fetchall()
    return {str(figure): str(value) for figure, value in rows}


Expected = dict[str, tuple[str | float, float]]  # figure -> (value, tolerance; 0 is exact text)


def _json(public: Path, path: str) -> Any:
    return json.loads((public / path.removeprefix("/")).read_text(encoding="utf-8"))


def _gravity(public: Path) -> Expected:
    q = _json(public, "/data/quality.json")
    ranges = q["summary"]["ranges"]
    return {
        "learn.fit_g": (q["hook"]["g_data"], HOOK_G_TOLERANCE),
        "summary.ranges.gravity_g_calibration": (ranges["gravity_g_calibration"], 0),
        "summary.ranges.gravity_g_control": (ranges["gravity_g_control"], 0),
    }


def _speed(public: Path) -> Expected:
    ex = _json(public, "/data/learn/speed.json")["example"]
    return {
        "learn.frames": (str(ex["frames"]), 0),
        "learn.ex_central_frames": (str(ex["full_precision"]["frames"]), 0),
    }


def _coordinates(public: Path) -> Expected:
    out: Expected = {}
    for stem in ("bb_possessions_possession-114086-1-36", "fb_possession_1874553_1"):
        rate = _json(public, f"/data/possessions/{stem}.json")["sample_rate_hz"]
        out[f"possession.{stem}.sample_rate_hz"] = (str(rate), 0)
    return out


def _rebound(public: Path) -> Expected:
    ex = _json(public, "/data/learn/rebound.json")["example"]
    times = ex["times"]
    ranked = sorted(times)
    # The file's times carry one more decimal than the page prints.
    return {
        "learn.ex_first_time": (ranked[0], 0.005),
        "learn.ex_second_time": (ranked[1], 0.005),
        "learn.ex_near_time": (times[ex["nearest"]], 0.005),
    }


def _cadence(public: Path) -> Expected:
    clip = _json(public, "/data/pose/hook_1925299.json")
    return {"learn.hook.1925299.cadence": (clip["windows"][0]["cadence_hz"], CADENCE_TOLERANCE)}


def _slope(public: Path, stem: str) -> float:
    """The least-squares slope of a possession's game clock on its video clock, by numpy."""
    frames = _json(public, f"/data/possessions/{stem}.json")["frames"]
    t = np.array([f["t"] for f in frames], np.float64) / 1000
    clock = np.array([f["clock"] for f in frames], np.float64)
    return float(np.polyfit(t, clock, 1)[0])


def _clock(public: Path) -> Expected:
    # The SQL's slopes, at five decimals, against numpy's on the same files; the ranges of the
    # medians against clock.json's own rows.
    rows = _json(public, "/data/learn/clock.json")["matches"]
    cal = [m["slope_median"] for m in rows if m["calibration"]]
    ctl = [m["slope_median"] for m in rows if not m["calibration"]]
    half = 0.000005 + 1e-12
    return {
        "learn.cal_slope": (_slope(public, "bb_possessions_possession-114086-1-36"), half),
        "learn.ctl_slope_all": (_slope(public, "bb_possessions_possession-184439-2-38"), half),
        "learn.cal_lo": (min(cal), 0),
        "learn.cal_hi": (max(cal), 0),
        "learn.ctl_lo": (min(ctl), 0),
        "learn.ctl_hi": (max(ctl), 0),
    }


EXPECT: dict[str, Callable[[Path], Expected]] = {
    "gravity": _gravity,
    "speed": _speed,
    "coordinates": _coordinates,
    "rebound": _rebound,
    "cadence": _cadence,
    "clock": _clock,
}


def compare(rows: dict[str, str], expected: Expected) -> list[str]:
    """What differs: a missing row, a text that is not the file's, a number off by more than its
    tolerance."""
    problems = []
    for figure, (want, tolerance) in expected.items():
        got = rows.get(figure)
        if got is None:
            problems.append(f"{figure}: no row")
        elif tolerance == 0:
            if got != str(want):
                problems.append(f"{figure}: {got}, the file's {want}")
        elif not math.isclose(float(got), float(want), rel_tol=0, abs_tol=tolerance):
            problems.append(f"{figure}: {got}, the file's {want} (within {tolerance})")
    return problems


def run_learn_browser(public: Path, *, check: bool = False) -> int:
    passed = 0
    for slug in LESSONS:
        sql = read(slug)
        missing = [f for f in sql.files if not (public / f.removeprefix("/")).is_file()]
        stray = undeclared(sql)
        if missing or stray:
            print(f"learn browser {slug}: files missing {missing}, read but not declared {stray}")
            continue
        rows = run(sql, public)
        expected = EXPECT[slug](public)
        problems = compare(rows, expected)
        for figure, value in rows.items():
            print(f"learn browser {slug}: {figure} = {value}")
        print(
            f"learn browser {slug}: {len(rows)} rows, {len(expected)} compared with the files, "
            f"{'equal' if not problems else 'DIFFERENT: ' + '; '.join(problems)}"
        )
        passed += not problems and bool(expected)
    total = len(LESSONS)
    if not check:
        return 0 if passed == total else 1
    if passed == total:
        print(
            f"learn browser --check: FULL {passed}/{total}: every query ran on web/public/data, "
            "read only its declared files and gave the files' figures; the rest is the e2e's"
        )
        return 0
    print(f"learn browser --check: {passed}/{total} lessons agree with their files")
    return 1
