"""`tracklab learn dribble` and the SQL of lesson 9's "Reproduce it".

A synthetic match in feet, like the public bundle. The ball's height is 1 m except near the
dribbles, where it falls 6 cm per frame towards a low point at 0.4 m:

- touch T1, dribbles at frames 100, 120, 140 and 143, low points at 100, 120 and 140: intervals
  0.8, 0.8 and 0.12 s, offsets 0, 0, 0 and -3, and the last two share the low point at 140;
- touch T2, dribbles at 300 and 318, low points at 302 and 318: interval 0.72 s, offsets 2 and 0;
- no touch: a dribble at 500 on its low point (offset 0); one at 400 between two equal low points
  at 396 and 401 (ties to the earliest: -4, not within 3 frames, where the latest would be); one
  at 600 with the ball missing at 603 (no window); one at 700 while the ball falls through the
  whole window (offset 5, at the edge).

So 10 dribbles, 4 intervals (median 0.76 s), 1 touch with three dribbles or more, 9 windows,
offsets -4, -3, 0, 0, 0, 0, 0, 2, 5 (7 of 9 within 3 frames, 1 at the edge), 4 pairs, 1 shared.
Mutations (a test that cannot fail protects nothing): the window at 4 frames (`REACH`), the time
at 30 fps, the heights in feet; on the SQL: intervals across touches, the lowest point of the
whole touch instead of the window, ties to the latest frame. Intervals across touches in Python
were run by hand (`touches` keyed by nothing): the median moves and the first test fails.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from tracklab.cli import main
from tracklab.learn import dribble as dr

FT = 0.3048
MATCH = int(dr.SQL_MATCH_ID)

DRIBBLES: list[tuple[str, str | None, int]] = [
    ("D1", "T1", 100),
    ("D2", "T1", 120),
    ("D3", "T1", 140),
    ("D4", "T1", 143),
    ("D5", "T2", 300),
    ("D6", "T2", 318),
    ("D7", None, 500),
    ("D8", None, 400),
    ("D9", None, 600),
    ("D10", None, 700),
]
LOWS = {(90, 150): (100, 120, 140), (290, 325): (302, 318), (490, 510): (500,)}


def _z(f: int) -> float | None:
    """The ball's height (m) at frame f."""
    if f == 603:
        return None
    if f in (396, 401):
        return 0.5
    if 690 <= f <= 710:
        return round(2.0 - 0.1 * (f - 695), 6)
    for (lo, hi), lows in LOWS.items():
        if lo <= f <= hi:
            return round(0.4 + 0.06 * min(abs(f - m) for m in lows), 6)
    return 1.0


FRAMES = range(0, 801)
WANT = {
    "dribbles": 10,
    "intervals": 4,
    "interval_median_s": 0.76,
    "interval_p10_s": 0.3,
    "interval_p90_s": 0.8,
    "touches_3": 1,
    "windows": 9,
    "offset_median": 0.0,
    "offset_abs_median": 0.0,
    "near_pct": 77.78,
    "edge_pct": 11.11,
    "low_z_median": 0.4,
    "pairs": 4,
    "shared_low": 1,
}


def write_bronze(root: Path) -> None:
    bronze = root / "bronze" / "basketball"
    for table in ("events_dribbles", "tracking_objects", "events_touches"):
        (bronze / table).mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE d (id VARCHAR, touchId VARCHAR, frame BIGINT)")
    con.executemany("INSERT INTO d VALUES (?, ?, ?)", DRIBBLES)
    con.execute("CREATE TABLE o (frameIdx BIGINT, side VARCHAR, z DOUBLE)")
    rows = [(f, "ball", None if (z := _z(f)) is None else z / FT) for f in FRAMES]
    con.executemany("INSERT INTO o VALUES (?, ?, ?)", [r for r in rows if r[2] is not None])
    con.execute("CREATE TABLE t (id VARCHAR, startFrame BIGINT, endFrame BIGINT)")
    con.executemany("INSERT INTO t VALUES (?, ?, ?)", [("T1", 95, 148), ("T2", 295, 322)])
    for name, table in (
        ("events_dribbles", "d"),
        ("tracking_objects", "o"),
        ("events_touches", "t"),
    ):
        path = (bronze / name / f"{MATCH}.parquet").as_posix()
        con.execute(f"COPY {table} TO '{path}' (FORMAT parquet)")


def write_raw(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    events = {"dribbles": [{"id": i, "touchId": t, "frame": f} for i, t, f in DRIBBLES]}
    (folder / f"{MATCH}_dynamic_events.json").write_text(json.dumps(events), encoding="utf-8")
    lines = []
    for f in FRAMES:
        z = _z(f)
        ball = {"xyz": None} if z is None else {"xyz": [0.0, 0.0, z / FT]}
        lines.append(json.dumps({"frameIdx": f, "ball": ball}))
    with gzip.open(folder / f"{MATCH}_tracking_data.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _figures(root: Path) -> dict[str, Any]:
    return dr.read_match(root / "bronze" / "basketball", MATCH)


def test_the_figures(tmp_path: Path) -> None:
    write_bronze(tmp_path)
    fig = _figures(tmp_path)
    print(f"learn dribble synthetic: {fig}")
    assert fig == WANT


def test_the_lowest_point_ties_to_the_earliest_frame() -> None:
    z = {f: 0.5 if f in (396, 401) else 1.0 for f in range(390, 411)}
    assert dr.lowest(z, 400) == (-4, 0.5)
    assert dr.lowest({**z, 405: None}, 400) is None  # type: ignore[dict-item]


def test_mutation_window_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_bronze(tmp_path)
    monkeypatch.setattr(dr, "REACH", 4)
    assert _figures(tmp_path) != WANT


def test_mutation_frame_rate_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_bronze(tmp_path)
    monkeypatch.setattr(dr, "FPS", 30)
    assert _figures(tmp_path)["interval_median_s"] != WANT["interval_median_s"]


def test_mutation_height_in_feet_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_bronze(tmp_path)
    monkeypatch.setattr(dr, "M_PER_FT", 1.0)
    assert _figures(tmp_path)["low_z_median"] != WANT["low_z_median"]


# The public SQL.


def test_the_sql_gives_the_figures_of_the_python(tmp_path: Path) -> None:
    write_raw(tmp_path / "m")
    got = dr.run_sql(dr.read_sql(), tmp_path / "m")
    print(f"learn dribble synthetic SQL: {got}")
    assert got == tuple(WANT[k] for k in dr.SQL_FIELDS)


SQL_MUTATIONS: dict[str, list[tuple[str, str]]] = {
    "intervals across touches": [
        ("OVER (PARTITION BY touch ORDER BY frame, id)) / 25", "OVER (ORDER BY frame, id)) / 25"),
        ("FROM dribble WHERE touch IS NOT NULL\n)", "FROM dribble\n)"),
    ],
    "the lowest point of the whole match": [
        (
            "ON ball.f BETWEEN frame - 5 AND frame + 5",
            "ON ball.f BETWEEN frame - 500 AND frame + 500",
        ),
        ("HAVING count(*) = 11", "HAVING count(*) > 0"),
    ],
    "ties to the latest frame": [("[ball.z, ball.f - frame]", "[ball.z, frame - ball.f]")],
}


@pytest.mark.parametrize("name", SQL_MUTATIONS)
def test_each_sql_mutation_changes_a_figure(tmp_path: Path, name: str) -> None:
    write_raw(tmp_path / "m")
    sql = dr.read_sql()
    for old, new in SQL_MUTATIONS[name]:
        assert old in sql, f"{name}: {old!r} is no longer in dribble.sql"
        sql = sql.replace(old, new)
    assert dr.run_sql(sql, tmp_path / "m") != tuple(WANT[k] for k in dr.SQL_FIELDS), name


def test_the_sql_names_its_match_in_its_file_names_and_is_lf() -> None:
    raw = dr.SQL_PATH.read_bytes()
    assert raw.count(dr.SQL_MATCH_ID.encode()) == dr.SQL_NAMES
    assert b"\r" not in raw


# The example and the command, on a data root made in tmp_path.

STEM = f"bb_possessions_possession-{MATCH}-1-1.json"


def write_possession(folder: Path) -> None:
    """A published possession over frames 80 to 330, the ball's height at two decimals."""
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    for f in range(80, 331):
        z = _z(f)
        row = [0, 0.0, 0.0, None if z is None else round(z, 2), 0]
        frames.append({"t": 40 * f, "clock": 0.0, "o": [row]})
    pos = {
        "match": {"match_id": f"bb:{MATCH}"},
        "entities": [{"i": 0, "entity_id": "bb:ball", "kind": "ball"}],
        "frames": frames,
    }
    (folder / STEM).write_text(json.dumps(pos), encoding="utf-8")


def test_the_example_is_the_touch_with_the_most_dribbles(tmp_path: Path) -> None:
    write_bronze(tmp_path)
    write_possession(tmp_path / "possessions")
    ex = dr.example_figures(tmp_path / "bronze" / "basketball", tmp_path / "possessions" / STEM)
    assert ex["touch_id"] == "T1"
    assert (ex["t0"], ex["t1"]) == (40 * 95, 40 * 148)
    assert [d["offset"] for d in ex["dribbles"]] == [0, 0, 0, -3]
    assert [d["t"] for d in ex["dribbles"]] == [4000, 4800, 5600, 5720]


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
    args = ["learn", "dribble", "--data-dir", str(root), "--out", str(out)]
    return main([*args, "--possessions", str(root.parent / "possessions"), *extra])


def test_the_file_is_written_lf_and_then_checks_full(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dr, "EXAMPLE_FILE", STEM)
    root = _root(tmp_path, raw=True)
    out = tmp_path / "learn" / "dribble.json"
    assert _run(root, out) == 0
    assert b"\r" not in out.read_bytes()
    assert _run(root, out, "--check") == 0
    assert "FULL 1/1" in capsys.readouterr().out


def test_the_check_is_partial_without_the_raw_files_and_fails_on_a_changed_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dr, "EXAMPLE_FILE", STEM)
    root = _root(tmp_path, raw=False)
    out = tmp_path / "dribble.json"
    assert _run(root, out) == 0
    assert _run(root, out, "--check") == 0
    assert "PARTIAL 0/1" in capsys.readouterr().out
    out.write_text(
        out.read_text(encoding="utf-8").replace('"windows": 9,', '"windows": 8,'),
        encoding="utf-8",
        newline="\n",
    )
    assert _run(root, out, "--check") == 1
    assert "differs from what bronze gives" in capsys.readouterr().out
