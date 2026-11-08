"""`tracklab learn possession` and the two queries of lesson 10's "Reproduce it".

Football, the match the public SQL names, seven phases (frames at 10 per second):

- period 1: team A from 0 to 100 and 100 to 150 (one run of two phases, 15 s); team B from 160 to
  200 (4 s); a phase with no team from 200 to 260; team B again from 260 to 300 (a new run, 4 s);
- period 2: team B from 1000 to 1100 (a new run: the period changed, 10 s); team A from 1100 to
  1180 (8 s).

So 7 phases, 5 runs, median 8 s, 90th percentile 13 s, 20 % of runs over more than one phase.
A second football match, held out by the fence, sits in the same bronze with other figures: it
must never be read. Basketball: three possessions of 10, 6 and 20 s and one with no end frame, so
3 possessions, median 10 s, 90th percentile 18 s. On the game clock, which counts down, the first
two last 6 and 4 s; the third has no clock at its end and the fourth no end frame, so 2
possessions, median 5 s, 90th percentile 5.8 s, ratio 1.16, under the exponential's log2 10.

Mutations (a test that cannot fail protects nothing): the fence's list emptied (the held-out
match enters and the fence test fails), the football frame rate at 25; on the SQL: runs across
periods, a phase with no team joined to its neighbours, possessions at 10 frames per second, the
clock read end minus start. In Python, runs across periods were run by hand (`last == (period,
team)` as `last[1] == team`): the run count drops to 4 and the first test fails. The clock was too
(task 162): `read_clock` without its `IS NOT NULL` on the clocks, and then with its subtraction
turned around; each time `test_the_clock` failed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from tracklab.cli import main
from tracklab.learn import possession as ps

FB = int(ps.FOOTBALL_SQL_ID)
BB = int(ps.BASKETBALL_SQL_ID)
HELD = sorted(ps.held_out())[0]  # read from the fence, never typed
A, B = 11, 22

PHASES: list[tuple[int, int, int, int, int | None]] = [
    (0, 0, 100, 1, A),
    (1, 100, 150, 1, A),
    (2, 160, 200, 1, B),
    (3, 200, 260, 1, None),
    (4, 260, 300, 1, B),
    (5, 1000, 1100, 2, B),
    (6, 1100, 1180, 2, A),
]
HELD_PHASES = [(0, 0, 50, 1, A), (1, 50, 900, 1, B)]
# period, startFrame, endFrame, offTeamId, startGameClock, endGameClock
POSSESSIONS = [
    (1, 0, 250, 7, 600.0, 594.0),
    (1, 250, 400, 8, 594.0, 590.0),
    (2, 1000, 1500, 7, 600.0, None),
    (2, 1600, None, 8, 580.0, 570.0),
]
FOOTBALL = {"phases": 7, "runs": 5, "run_median_s": 8.0, "run_p90_s": 13.0, "multi_phase_pct": 20.0}
BASKETBALL = {
    "possessions": 3,
    "median_s": 10.0,
    "p90_s": 18.0,
    "clock_possessions": 2,
    "clock_median_s": 5.0,
    "clock_p90_s": 5.8,
}


def write_bronze(root: Path) -> None:
    fb = root / "bronze" / "football" / "phases_of_play"
    bb = root / "bronze" / "basketball" / "events_possessions"
    fb.mkdir(parents=True, exist_ok=True)
    bb.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for match, rows in ((FB, PHASES), (int(HELD), HELD_PHASES)):
        con.execute(
            "CREATE OR REPLACE TABLE p (index BIGINT, frame_start BIGINT, frame_end BIGINT, "
            "period BIGINT, team_in_possession_id BIGINT, duration DOUBLE)"
        )
        con.executemany("INSERT INTO p VALUES (?, ?, ?, ?, ?, 0)", rows)
        con.execute(f"COPY p TO '{(fb / f'{match}.parquet').as_posix()}' (FORMAT parquet)")
    con.execute(
        "CREATE TABLE q (id VARCHAR, period BIGINT, startFrame BIGINT, endFrame BIGINT, "
        "offTeamId BIGINT, startGameClock DOUBLE, endGameClock DOUBLE)"
    )
    con.executemany(
        "INSERT INTO q VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(f"p{i}", *row) for i, row in enumerate(POSSESSIONS)],
    )
    con.execute(f"COPY q TO '{(bb / f'{BB}.parquet').as_posix()}' (FORMAT parquet)")


def write_raw(root: Path) -> dict[str, Path]:
    """The two repositories' folders, as the SQL expects them under their own names."""
    fb = root / "opendata"
    folder = fb / "data" / "matches" / str(FB)
    folder.mkdir(parents=True)
    lines = ["index,match_id,frame_start,frame_end,period,team_in_possession_id,duration"]
    lines += [f"{i},{FB},{a},{b},{p},{'' if t is None else t},0" for i, a, b, p, t in PHASES]
    (folder / f"{FB}_phases_of_play.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    bb = root / "opendata-basketball"
    folder = bb / "data" / "matches" / str(BB)
    folder.mkdir(parents=True)
    events = {
        "possessions": [
            {
                "id": f"p{i}",
                "period": p,
                "startFrame": a,
                "endFrame": b,
                "offTeamId": t,
                "startGameClock": c0,
                "endGameClock": c1,
            }
            for i, (p, a, b, t, c0, c1) in enumerate(POSSESSIONS)
        ]
    }
    (folder / f"{BB}_dynamic_events.json").write_text(json.dumps(events), encoding="utf-8")
    return {"opendata": fb, "opendata-basketball": bb}


def test_the_figures(tmp_path: Path) -> None:
    write_bronze(tmp_path)
    fb = tmp_path / "bronze" / "football"
    bb = tmp_path / "bronze" / "basketball"
    assert ps.football_figures(ps.read_phases(fb, FB)) == FOOTBALL
    row = ps.basketball_row(bb, BB)
    assert {k: row[k] for k in BASKETBALL} == BASKETBALL


def test_the_clock(tmp_path: Path) -> None:
    """Start minus end, only possessions with both frames and both clocks, and the ratio."""
    write_bronze(tmp_path)
    bb = tmp_path / "bronze" / "basketball"
    assert ps.read_clock(bb, BB) == [6.0, 4.0]
    row = ps.basketball_row(bb, BB)
    assert row["clock_p90_over_median"] == 1.16
    assert ps.clock_above_exp([row]) == 0
    assert ps.clock_above_exp([{**row, "clock_p90_over_median": 3.33}]) == 1


def test_a_held_out_match_is_never_read(tmp_path: Path) -> None:
    write_bronze(tmp_path)
    assert ps.football_matches(tmp_path / "bronze" / "football") == [FB]
    text = ps.render(ps.build(tmp_path))
    assert HELD not in text
    assert [m["match_id"] for m in json.loads(text)["football"]["matches"]] == [f"fb:{FB}"]


def test_mutation_fence_emptied_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_bronze(tmp_path)
    monkeypatch.setattr(ps, "held_out", set)
    with pytest.raises(AssertionError):
        test_a_held_out_match_is_never_read(tmp_path)


def test_mutation_frame_rate_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_bronze(tmp_path)
    monkeypatch.setattr(ps, "FOOTBALL_HZ", 25)
    fb = tmp_path / "bronze" / "football"
    assert ps.football_figures(ps.read_phases(fb, FB)) != FOOTBALL


def test_the_published_file_keeps_the_fence() -> None:
    """The file the site serves: ten football matches, none held out, the timeline's included."""
    path = Path(__file__).resolve().parents[3] / "web" / "public" / "data" / "learn"
    data = json.loads((path / "possession.json").read_text(encoding="utf-8"))
    ids = [m["match_id"].removeprefix("fb:") for m in data["football"]["matches"]]
    assert len(ids) == 10
    assert set(ids).isdisjoint(ps.held_out())
    assert data["football"]["timeline"]["match_id"].removeprefix("fb:") in ids


# The public SQL.


def test_the_sql_gives_the_figures_of_the_python(tmp_path: Path) -> None:
    roots = write_raw(tmp_path)
    football, basketball = ps.read_sql()
    fb = ps.run_sql(football, {"opendata": roots["opendata"]}, ps.FOOTBALL_FIELDS)
    bb = ps.run_sql(
        basketball, {"opendata-basketball": roots["opendata-basketball"]}, ps.BASKETBALL_FIELDS
    )
    print(f"learn possession synthetic SQL: {fb} {bb}")
    assert fb == tuple(FOOTBALL[k] for k in ps.FOOTBALL_FIELDS)
    assert bb == tuple(BASKETBALL[k] for k in ps.BASKETBALL_FIELDS)


SQL_MUTATIONS: dict[str, tuple[int, list[tuple[str, str]]]] = {
    "runs across periods": (
        0,
        [
            ("WINDOW w AS (PARTITION BY period ORDER BY index)", "WINDOW w AS (ORDER BY index)"),
            (
                "sum(starts) OVER (PARTITION BY period ORDER BY index)",
                "sum(starts) OVER (ORDER BY index)",
            ),
            ("SELECT period, run, count(*)", "SELECT any_value(period), run, count(*)"),
            ("GROUP BY period, run", "GROUP BY run"),
        ],
    ),
    "a phase with no team joined to its neighbours": (
        0,
        [
            ("  FROM read_csv(", "  FROM (SELECT * FROM read_csv("),
            (".csv')\n", ".csv') WHERE team_in_possession_id IS NOT NULL)\n"),
        ],
    ),
    "possessions at 10 frames per second": (1, [("p.startFrame) / 25", "p.startFrame) / 10")]),
    "the clock read end minus start": (
        1,
        [("p.startGameClock - p.endGameClock", "p.endGameClock - p.startGameClock")],
    ),
}


@pytest.mark.parametrize("name", SQL_MUTATIONS)
def test_each_sql_mutation_changes_a_figure(tmp_path: Path, name: str) -> None:
    roots = write_raw(tmp_path)
    which, changes = SQL_MUTATIONS[name]
    sql = ps.read_sql()[which]
    for old, new in changes:
        assert old in sql, f"{name}: {old!r} is no longer in possession.sql"
        sql = sql.replace(old, new)
    if which == 0:
        got = ps.run_sql(sql, {"opendata": roots["opendata"]}, ps.FOOTBALL_FIELDS)
        assert got != tuple(FOOTBALL[k] for k in ps.FOOTBALL_FIELDS), name
    else:
        got = ps.run_sql(
            sql, {"opendata-basketball": roots["opendata-basketball"]}, ps.BASKETBALL_FIELDS
        )
        assert got != tuple(BASKETBALL[k] for k in ps.BASKETBALL_FIELDS), name


def test_each_query_names_its_match_twice_and_the_file_is_lf() -> None:
    football, basketball = ps.read_sql()
    assert football.count(ps.FOOTBALL_SQL_ID) == ps.SQL_NAMES
    assert basketball.count(ps.BASKETBALL_SQL_ID) == ps.SQL_NAMES
    assert b"\r" not in ps.SQL_PATH.read_bytes()


# The command, on a data root made in tmp_path.


def _root(tmp_path: Path, *, raw: bool) -> Path:
    root = tmp_path / "data"
    write_bronze(root)
    if raw:
        roots = write_raw(tmp_path / "clones")
        for source, repo in (
            ("opendata-football", "opendata"),
            ("opendata-basketball", "opendata-basketball"),
        ):
            receipt = root / "raw" / source
            receipt.mkdir(parents=True)
            text = json.dumps({"failed": [], "source_path": str(roots[repo])})
            (receipt / "_receipt.json").write_text(text, encoding="utf-8")
    return root


def _run(root: Path, out: Path, *extra: str) -> int:
    return main(["learn", "possession", "--data-dir", str(root), "--out", str(out), *extra])


def test_the_file_is_written_lf_and_then_checks_full(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path, raw=True)
    out = tmp_path / "learn" / "possession.json"
    assert _run(root, out) == 0
    assert b"\r" not in out.read_bytes()
    assert _run(root, out, "--check") == 0
    assert "football FULL 1/1, basketball FULL 1/1" in capsys.readouterr().out


def test_the_check_is_partial_without_the_raw_files_and_fails_on_a_changed_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path, raw=False)
    out = tmp_path / "possession.json"
    assert _run(root, out) == 0
    assert _run(root, out, "--check") == 0
    assert "football PARTIAL 0/1, basketball PARTIAL 0/1" in capsys.readouterr().out
    text = out.read_text(encoding="utf-8")
    out.write_text(text.replace('"runs": 5,', '"runs": 6,'), encoding="utf-8", newline="\n")
    assert _run(root, out, "--check") == 1
    assert "differs from what bronze gives" in capsys.readouterr().out


def test_the_check_fails_on_a_held_out_match_in_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path, raw=False)
    out = tmp_path / "possession.json"
    assert _run(root, out) == 0
    data: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    data["football"]["matches"].append({**data["football"]["matches"][0], "match_id": f"fb:{HELD}"})
    out.write_text(ps.render(data), encoding="utf-8", newline="\n")
    assert _run(root, out, "--check") == 1
    assert "holds held-out matches" in capsys.readouterr().out


@pytest.mark.parametrize("median", [None, 0.0])
def test_the_shape_check_warns_and_does_not_crash_on_a_match_without_a_clock(
    tmp_path: Path, median: float | None
) -> None:
    root = _root(tmp_path, raw=False)
    out = tmp_path / "possession.json"
    assert _run(root, out) == 0
    data: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    assert ps._shape_problems(data) == ""
    row = data["basketball"]["matches"][0]
    row.update(clock_median_s=median, clock_p90_s=None if median is None else 0.0)
    row["clock_p90_over_median"] = None
    assert ps._shape_problems(data) == ""
    row["clock_p90_over_median"] = 1.0
    assert "the clock's ratio" in ps._shape_problems(data)
