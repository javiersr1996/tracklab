"""`tracklab learn browser`: the queries of "Run it here", run on the published files (task 86).

Each lesson of P8 has a `<slug>.browser.sql`: a `-- files:` line with the files under
`web/public/data` it reads (by their path on the site, `/data/...`), the `CREATE VIEW` statements
that flatten them, and one query whose rows are `(figure, value)`: the name of a `data-fig` the
lesson prints and the value the query computes for it. The page reads the same file at build time:
it registers the files, creates the views and puts the query in the box, and the browser compares
each row with the figure of that name (`matched k of n`, e2e/learn-reproduce.spec.ts).

This module runs the same statements with DuckDB on `web/public/data`, the `/data/` paths pointed
at that folder, and compares the rows it can with the files themselves: a figure the files carry
(a sample rate, a count of frames) is compared exactly, and a figure only the lesson's TypeScript
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

from tracklab.learn import facing as facing_script

LESSONS = (
    "gravity",
    "speed",
    "coordinates",
    "rebound",
    "cadence",
    "clock",
    "pass",
    "entry",
    "dribble",
    "possession",
    "facing",
    "expected-points",
)
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
    # The SQL's slopes, at five decimals, against numpy's on the same files. The ranges of the
    # medians are clock.json's rows read back (the medians run over possessions the site does not
    # publish), so there is nothing here to compare them with: they are the e2e's.
    half = 0.000005 + 1e-12
    return {
        "learn.cal_slope": (_slope(public, "bb_possessions_possession-114086-1-36"), half),
        "learn.ctl_slope_all": (_slope(public, "bb_possessions_possession-184439-2-38"), half),
    }


def _pass(public: Path) -> Expected:
    # The SQL's chords and paths, at two decimals, against pass.json's at four (computed by the
    # pipeline from the same published positions); its chord speeds against the file's exactly.
    out: Expected = {}
    for i, p in enumerate(_json(public, "/data/learn/pass.json")["example"]["passes"]):
        out[f"learn.passes.{i}.chord_m"] = (p["chord_m"], 0.005 + 1e-9)
        out[f"learn.passes.{i}.path_m"] = (p["path_m"], 0.005 + 1e-9)
        out[f"learn.passes.{i}.chord_speed"] = (p["chord_speed"], 0)
    return out


def _entry(public: Path) -> Expected:
    # The SQL's run of the check on the example's samples against the angles the pipeline
    # computed from the same published samples with `entry.py` (`published` of entry.json).
    pub = _json(public, "/data/learn/entry.json")["example"]["published"]
    return {
        "learn.ex_k": (str(pub["k"]), 0),
        "learn.ex_reported": (str(pub["reported"]), 0),
        "learn.ex_required": (str(pub["required"]), 0),
        "learn.ex_v_h": (pub["v_h"], 0.005 + 1e-9),
    }


def _dribble(public: Path) -> Expected:
    # The SQL's offsets and lowest heights against the ones the pipeline computed from the same
    # published heights (dribble.json's example); the median interval against numpy's.
    ex = _json(public, "/data/learn/dribble.json")["example"]
    out: Expected = {}
    for i, d in enumerate(ex["dribbles"]):
        out[f"learn.dribbles.{i}.offset"] = (str(d["offset"]), 0)
        out[f"learn.dribbles.{i}.low_z"] = (str(d["low_z"]), 0)
    gaps = np.diff([d["t"] for d in ex["dribbles"]]) / 1000
    out["learn.ex_median_s"] = (float(np.median(gaps)), 0.005 + 1e-9)
    return out


def _possession(public: Path) -> Expected:
    # The SQL's rows from the two timelines against the per-match rows the pipeline computed from
    # bronze, and its shares beyond twice the median against numpy's on the same timelines.
    doc = _json(public, "/data/learn/possession.json")
    out: Expected = {}
    for sport, fields in (
        ("football", ("runs", "run_median_s", "run_p90_s", "multi_phase_pct")),
        ("basketball", ("possessions", "median_s", "p90_s")),
    ):
        match_id = doc[sport]["timeline"]["match_id"]
        row = next(m for m in doc[sport]["matches"] if m["match_id"] == match_id)
        for f in fields:
            out[f"possession.{sport}.matches.{match_id}.{f}"] = (row[f], 1e-9)
        s = np.array([r[2] - r[1] for r in doc[sport]["timeline"]["rows"]])
        share = 100 * float(np.mean(s > 2 * np.quantile(s, 0.5)))
        out[f"learn.{sport[0]}b.beyond2_pct"] = (share, 0.05 + 1e-9)
    return out


def _facing(public: Path) -> Expected:
    # The SQL's angles for the hook player of the clip against the public script's on the same
    # clip (`facing.py`, the lesson's "Reproduce it"), at the three decimals the page prints.
    clip = _json(public, "/data/pose/hook_1925299.json")
    frames = facing_script.frames_of(clip, clip["windows"][0]["player"])
    s = facing_script.summary(frames)
    first = frames[0]
    half = 0.0005 + 1e-9
    return {
        "learn.hook.1925299.frames": (str(s["frames"]), 0),
        "learn.hook.1925299.first_frame_id": (str(first["f"]), 0),
        "learn.hook.1925299.first_facing": (first["facing"], half),
        "learn.hook.1925299.first_heading": (first["heading"], half),
        "learn.hook.1925299.first_relative": (first["relative"], half),
        "learn.hook.1925299.median_abs": (s["median_abs"], half),
        "learn.hook.1925299.circ_mean": (s["circ_mean"], half),
        "learn.hook.1925299.resultant": (s["resultant"], half),
        "learn.hook.1925299.circ_var": (s["circ_var"], half),
        "learn.hook.1925299.off_pct": (s["off_pct"], 0.05 + 1e-9),
        "learn.hook.1925299.back_pct": (s["back_pct"], 0.05 + 1e-9),
    }


def _expected_points(public: Path) -> Expected:
    # The SQL's points per attempt, means and per-team figures from the counts against the ones
    # `euroleague publish` wrote next to them (the file's own, exactly); the plain mean of the
    # classes, which the file does not carry, against Python's on the same counts.
    doc = _json(public, "/data/euroleague/expected-points.json")
    out: Expected = {}
    for s in doc["seasons"]:
        season = s["season"]
        for zone, value in s["pps"].items():
            out[f"xp.{season}.pps.{zone}"] = (value, 1e-9)
        out[f"xp.{season}.mean"] = (s["mean"], 1e-9)
        plain = sum(s["league"][c]["pts"] / s["league"][c]["n"] for c in doc["classes"]) / 3
        out[f"learn.season.{season}.plain"] = (plain, 0.0005 + 1e-9)
        for team in s["teams"]:
            for field in ("pps", "xpps", "mix", "making"):
                out[f"xp.{season}.teams.{team['code']}.{field}"] = (team[field], 1e-9)
    return out


EXPECT: dict[str, Callable[[Path], Expected]] = {
    "gravity": _gravity,
    "speed": _speed,
    "coordinates": _coordinates,
    "rebound": _rebound,
    "cadence": _cadence,
    "clock": _clock,
    "pass": _pass,
    "entry": _entry,
    "dribble": _dribble,
    "possession": _possession,
    "facing": _facing,
    "expected-points": _expected_points,
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
