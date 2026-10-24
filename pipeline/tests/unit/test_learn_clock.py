"""`tracklab learn clock` and the SQL of lesson 6's "Reproduce it".

A synthetic match, 25 fps, `wallClock` = 40 ms a frame:

- period 1, frames 0 to 199: the clock runs and counts down exactly 0.04 s a frame (slope -1);
- frames 200 to 209: the flag says stopped;
- frames 210 to 359: the flag says running, the clock holds for its first 15 frames, then counts
  down (14 held steps, a slope above -1);
- frame 360 has no game clock; frames 361 to 439 run at half speed (79 frames, too short);
- period 2, frames 440 to 589: the clock counts down at -1 again. Without the period break, the
  short run and this one would make one segment of 229 frames.

So three segments, 500 frames, 497 steps, 14 held, and the median slope is -1. Each test that
checks a figure also runs one mutation of the code behind it (a test that cannot fail protects
nothing): segments from 25 frames (the short run enters and the median moves), no period break
(the frames change), a slope through the origin at 3,600 s instead of about the mean (it moves,
in the tenth decimal), and on the SQL: no `held`, no length rule, no period in the run.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pytest

from tracklab.cli import main
from tracklab.learn import clock as cl

MATCH = int(cl.SQL_MATCH_ID)
STEM = f"bb_possessions_possession-{MATCH}-1-1.json"


def _frames() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(f: int, clock: float | None, stopped: bool, period: int) -> None:
        rows.append(
            {
                "frameIdx": f,
                "wallClock": 40 * f,
                "gameClock": clock,
                "gameClockStopped": stopped,
                "period": period,
            }
        )

    for f in range(0, 200):
        add(f, round(600 - 0.04 * f, 2), False, 1)
    for f in range(200, 210):
        add(f, 592.0, True, 1)
    for f in range(210, 360):
        add(f, round(592.0 - 0.04 * max(0, f - 224), 2), False, 1)
    add(360, None, False, 1)
    for f in range(361, 440):
        add(f, round(586.0 - 0.02 * (f - 361), 2), False, 1)
    for f in range(440, 590):
        add(f, round(600 - 0.04 * (f - 440), 2), False, 2)
    return rows


def write_bronze(root: Path) -> None:
    folder = root / "bronze" / "basketball" / "tracking_frames"
    folder.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE f (frameIdx BIGINT, wallClock BIGINT, gameClock DOUBLE, "
        "gameClockStopped BOOLEAN, period SMALLINT)"
    )
    con.executemany(
        "INSERT INTO f VALUES (?, ?, ?, ?, ?)",
        [list(r.values()) for r in _frames()],
    )
    con.execute(f"COPY f TO '{(folder / f'{MATCH}.parquet').as_posix()}' (FORMAT parquet)")


def write_raw(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({**r, "homePlayers": [], "awayPlayers": [], "ball": {}}) for r in _frames()]
    with gzip.open(folder / f"{MATCH}_tracking_data.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def write_possession(folder: Path) -> None:
    """A published possession over frames 195 to 230: the flag says stopped from 200 to 209."""
    folder.mkdir(parents=True, exist_ok=True)
    by_frame = {r["frameIdx"]: r for r in _frames()}
    frames = [{"t": 40 * f, "clock": by_frame[f]["gameClock"], "o": []} for f in range(195, 231)]
    pos = {"match": {"match_id": f"bb:{MATCH}"}, "frames": frames}
    (folder / STEM).write_text(json.dumps(pos), encoding="utf-8")


def _figures(root: Path) -> dict[str, Any]:
    path = root / "bronze" / "basketball" / "tracking_frames" / f"{MATCH}.parquet"
    return cl.match_figures(*cl.read_running(path))


WANT = {
    "segments": 3,
    "frames": 500,
    "steps": 497,
    "held": 14,
    "slope_median": -1.0,
    "slope_q1": -1.0,
}


def test_the_segments_and_their_slopes(tmp_path: Path) -> None:
    write_bronze(tmp_path)
    fig = _figures(tmp_path)
    print(f"learn clock synthetic: {fig}")
    assert {k: fig[k] for k in WANT} == WANT
    assert -1.0 < fig["slope_q3"] < -0.95  # the held segment, halfway to the median


def test_the_slope_is_exact_on_a_line_and_its_mutation_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t = 3600.0 + np.arange(200) / 25
    clock = 600 - 0.999 * (t - t[0])
    assert cl.slope(t, clock) == pytest.approx(-0.999, abs=1e-12)

    def through_origin(t: np.ndarray, clock: np.ndarray) -> float:  # type: ignore[type-arg]
        n = len(t)
        return float(
            (n * np.sum(t * clock) - t.sum() * clock.sum()) / (n * np.sum(t * t) - t.sum() ** 2)
        )

    monkeypatch.setattr(cl, "slope", through_origin)
    off = abs(cl.slope(t, clock) + 0.999)
    print(f"learn clock: the slope through the origin is off by {off:.2e}")
    assert off > 1e-12


def test_mutation_short_segments_moves_the_median(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_bronze(tmp_path)
    monkeypatch.setattr(cl, "MIN_FRAMES", 25)
    fig = _figures(tmp_path)
    assert fig["segments"] == 4
    assert fig["slope_median"] != WANT["slope_median"]


def test_mutation_no_period_break_changes_the_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_bronze(tmp_path)
    real = cl.segments
    monkeypatch.setattr(cl, "segments", lambda period, frame: real(np.zeros_like(period), frame))
    assert _figures(tmp_path)["frames"] != WANT["frames"]


def test_the_example_gives_the_flag_stops_inside_the_possession(tmp_path: Path) -> None:
    write_bronze(tmp_path)
    write_possession(tmp_path / "possessions")
    ex = cl.example_figures(tmp_path / "bronze" / "basketball", tmp_path / "possessions" / STEM)
    assert ex["stopped"] == [[40 * 200, 40 * 209]]
    assert ex["frames"] == 36


# The public SQL.


def test_the_sql_gives_the_figures_of_the_python(tmp_path: Path) -> None:
    write_raw(tmp_path / "m")
    write_bronze(tmp_path)
    got = cl.run_sql(cl.read_sql(), tmp_path / "m")
    fig = _figures(tmp_path)
    print(f"learn clock synthetic SQL: {got}")
    assert got == tuple(fig[k] for k in cl.SQL_FIELDS)


SQL_MUTATIONS: dict[str, list[tuple[str, str]]] = {
    "no held steps": [("clock = lag(clock)", "clock <> lag(clock)")],
    "no length rule": [("HAVING count(*) >= 125", "HAVING count(*) >= 25")],
    "no period in the run": [
        ("PARTITION BY period ORDER BY frameIdx) AS run", "ORDER BY frameIdx) AS run"),
        ("GROUP BY period, run", "GROUP BY run"),
        ("PARTITION BY period, run", "PARTITION BY run"),
    ],
}


@pytest.mark.parametrize("name", SQL_MUTATIONS)
def test_each_sql_mutation_changes_a_figure(tmp_path: Path, name: str) -> None:
    write_raw(tmp_path / "m")
    write_bronze(tmp_path)
    sql = cl.read_sql()
    for old, new in SQL_MUTATIONS[name]:
        assert old in sql, f"{name}: {old!r} is no longer in clock.sql"
        sql = sql.replace(old, new)
    want = tuple(_figures(tmp_path)[k] for k in cl.SQL_FIELDS)
    assert cl.run_sql(sql, tmp_path / "m") != want, name


def test_the_sql_names_its_match_once_and_is_lf() -> None:
    raw = cl.SQL_PATH.read_bytes()
    assert raw.count(cl.SQL_MATCH_ID.encode()) == 1
    assert b"\r" not in raw


# The command, on a data root made in tmp_path.


def _root(tmp_path: Path, *, raw: bool) -> Path:
    root = tmp_path / "data"
    write_bronze(root)
    write_possession(tmp_path / "possessions")
    if raw:
        receipt = root / "raw" / "opendata-basketball"
        receipt.mkdir(parents=True)
        (receipt / "_receipt.json").write_text(json.dumps({"failed": []}), encoding="utf-8")
        write_raw(receipt / "data" / "matches" / str(MATCH))
    return root


def _run(root: Path, out: Path, *extra: str) -> int:
    possessions = root.parent / "possessions"
    args = ["learn", "clock", "--data-dir", str(root), "--out", str(out)]
    return main([*args, "--possessions", str(possessions), *extra])


def test_the_file_is_written_lf_and_then_checks_full(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cl, "EXAMPLES", (STEM,))
    root = _root(tmp_path, raw=True)
    out = tmp_path / "learn" / "clock.json"
    assert _run(root, out) == 0
    assert b"\r" not in out.read_bytes()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["matches"][0]["held"] == WANT["held"]
    assert _run(root, out, "--check") == 0
    assert "FULL 1/1" in capsys.readouterr().out


def test_the_check_is_partial_without_the_raw_files_and_fails_on_a_changed_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cl, "EXAMPLES", (STEM,))
    root = _root(tmp_path, raw=False)
    out = tmp_path / "clock.json"
    assert _run(root, out) == 0
    assert _run(root, out, "--check") == 0
    assert "PARTIAL 0/1" in capsys.readouterr().out
    out.write_text(
        out.read_text(encoding="utf-8").replace('"held": 14,', '"held": 13,'),
        encoding="utf-8",
        newline="\n",
    )
    assert _run(root, out, "--check") == 1
    assert "differs from what bronze gives" in capsys.readouterr().out
