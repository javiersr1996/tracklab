"""`tracklab learn speed` and the SQL of lesson 2's "Reproduce it".

A synthetic match, in feet and at 25 fps like the public bundle: two players on smooth curved
paths, one of them missing for five frames, and a `speed` field that is *exactly* the central
difference of each player's own positions. So on every triple the gap is zero and r is one;
every other estimate leaves a gap. Each test that checks a figure also runs one mutation of the
function behind it and asserts the synthetic tells the two apart (a test that cannot fail
protects nothing):

- `CENTRAL` replaced by the forward difference: the median gap is no longer zero;
- `contiguous` ignoring frames and players: the triples across the hole and across the change of
  player enter, and their gap is far from zero;
- `smoothed` without its division by k: the moving average of a field built as one stops
  matching;
- `shaw_rows` with no max-speed cut: the rows around a jump over 12 m/s stay;
- the SQL without its contiguity test or without its partition by player: `triples` changes.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

import duckdb
import numpy as np
import pytest

from tracklab.cli import main
from tracklab.learn import speed as sp

FT = 0.3048
FPS = 25
FRAMES = range(0, 200)
HOLE = range(100, 105)  # player 7 is not in the file at these frames
EXAMPLE_PLAYER = 59191
MATCH = 114099
EX_FRAMES = range(50, 90)  # the synthetic possession


def _path(player: int, f: int) -> tuple[float, float]:
    """Position in feet at frame f: curved, never at constant speed."""
    t = f / FPS
    if player == EXAMPLE_PLAYER:
        return -10.0 + 6.0 * t + 2.0 * math.sin(1.5 * t), 3.0 * math.cos(0.8 * t)
    return 20.0 - 4.0 * t + 0.5 * t * t, -5.0 + 2.5 * math.sin(2.0 * t)


def _present(player: int) -> list[int]:
    return [f for f in FRAMES if not (player == 7 and f in HOLE)]


def _speed_ft(player: int, f: int, k: int = 1) -> float:
    """The central difference at f, or a moving average of k of them (where defined)."""
    half = (k - 1) // 2
    vx = vy = 0.0
    for j in range(f - half, f + half + 1):
        (xa, ya), (xb, yb) = _path(player, j + 1), _path(player, j - 1)
        vx += (xa - xb) * FPS / 2 / k
        vy += (ya - yb) * FPS / 2 / k
    return math.hypot(vx, vy)


def _rows(k: int = 1) -> list[dict[str, float | int | str]]:
    out: list[dict[str, float | int | str]] = []
    for player, side in ((EXAMPLE_PLAYER, "home"), (7, "away")):
        for f in _present(player):
            x, y = _path(player, f)
            out.append(
                {
                    "side": side,
                    "playerId": player,
                    "frameIdx": f,
                    "x": x,
                    "y": y,
                    "speed": _speed_ft(player, f, k),
                }
            )
    return out


def write_bronze(root: Path, rows: list[dict[str, float | int | str]]) -> None:
    con = duckdb.connect()
    for table in ("tracking_objects", "tracking_frames"):
        (root / "bronze" / "basketball" / table).mkdir(parents=True, exist_ok=True)
    con.execute(
        "CREATE TABLE o (side VARCHAR, playerId BIGINT, frameIdx BIGINT, x DOUBLE, y DOUBLE, "
        "speed DOUBLE)"
    )
    con.executemany(
        "INSERT INTO o VALUES (?, ?, ?, ?, ?, ?)",
        [[r["side"], r["playerId"], r["frameIdx"], r["x"], r["y"], r["speed"]] for r in rows],
    )
    con.execute("INSERT INTO o VALUES ('ball', NULL, 0, 0, 0, 99.0)")  # never a player
    objects = root / "bronze" / "basketball" / "tracking_objects" / f"{MATCH}.parquet"
    frames = root / "bronze" / "basketball" / "tracking_frames" / f"{MATCH}.parquet"
    con.execute(f"COPY o TO '{objects.as_posix()}' (FORMAT parquet)")
    con.execute(
        f"COPY (SELECT range AS frameIdx, range * 40 AS wallClock FROM range(0, 200)) "
        f"TO '{frames.as_posix()}' (FORMAT parquet)"
    )


def write_raw(folder: Path, rows: list[dict[str, float | int | str]]) -> None:
    """The match's public tracking file: one line per frame, players in two lists."""
    folder.mkdir(parents=True, exist_ok=True)
    by_frame: dict[int, dict[str, list[dict[str, object]]]] = {}
    for r in rows:
        frame = by_frame.setdefault(int(r["frameIdx"]), {"home": [], "away": []})
        frame[str(r["side"])].append(
            {
                "xyz": [r["x"], r["y"], 0.0],
                "speed": r["speed"],
                "jersey": "9",
                "playerId": r["playerId"],
            }
        )
    lines = [
        json.dumps(
            {
                "frameIdx": f,
                "wallClock": f * 40,
                "homePlayers": p["home"],
                "awayPlayers": p["away"],
                "ball": {},
            }
        )
        for f, p in sorted(by_frame.items())
    ]
    with gzip.open(folder / f"{MATCH}_tracking_data.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def write_possession(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    for f in EX_FRAMES:
        x, y = _path(EXAMPLE_PLAYER, f)
        frames.append(
            {"t": f * 40, "clock": 0.0, "o": [[0, round(x * FT, 2), round(y * FT, 2), None, 1]]}
        )
    payload = {
        "possession_id": "bb:possessions:possession-114099-1-41",
        "match": {"match_id": f"bb:{MATCH}"},
        "entities": [{"i": 0, "entity_id": f"bb:{EXAMPLE_PLAYER}", "kind": "player"}],
        "frames": frames,
    }
    (folder / sp.EXAMPLE_FILE).write_text(json.dumps(payload), encoding="utf-8")


def _track(rows: list[dict[str, float | int | str]]) -> sp.Track:
    ordered = sorted(rows, key=lambda r: (int(r["playerId"]), int(r["frameIdx"])))
    col = lambda k: np.array([r[k] for r in ordered])  # noqa: E731
    return sp.Track(
        col("playerId").astype(np.int64),
        col("frameIdx").astype(np.int64),
        col("x").astype(np.float64) * FT,
        col("y").astype(np.float64) * FT,
        col("speed").astype(np.float64) * FT,
    )


def _expected_triples() -> int:
    return sum(
        1
        for p in (EXAMPLE_PLAYER, 7)
        for f in _present(p)
        if f - 1 in _present(p) and f + 1 in _present(p)
    )


# The figures.


def test_a_speed_built_as_the_central_difference_has_no_gap() -> None:
    fig = sp.match_figures(_track(_rows()))
    print(f"learn speed synthetic: {fig}")
    assert fig["triples"] == _expected_triples()
    assert fig["r"] == 1.0
    assert fig["median_gap"] == 0.0 and fig["p99_gap"] == 0.0
    assert fig["median_gap_forward"] > 0.01 and fig["median_gap_backward"] > 0.01
    assert fig["by_window"]["1"] == 0.0 and fig["by_window"]["5"] > 0.0


def test_mutation_forward_for_central_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "CENTRAL", sp.FORWARD)
    assert sp.match_figures(_track(_rows()))["median_gap"] > 0.01


def test_contiguity_keeps_only_whole_triples_and_its_mutation_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t = _track(_rows())
    assert int(sp.contiguous(t, 1).sum()) == _expected_triples()

    def every_inner_row(t: sp.Track, reach: int) -> np.ndarray:  # type: ignore[type-arg]
        ok = np.zeros(len(t.frame), np.bool_)
        ok[reach : len(t.frame) - reach] = True
        return ok

    monkeypatch.setattr(sp, "contiguous", every_inner_row)
    fig = sp.match_figures(t)
    assert fig["triples"] > _expected_triples()
    assert fig["p99_gap"] > 0.0  # the rows across the hole and across the change of player


def test_a_moving_average_is_one_longer_difference() -> None:
    h = 1 / FPS
    got = sp.smoothed(sp.CENTRAL, 3)
    want = {-2: -1 / (6 * h), -1: -1 / (6 * h), 1: 1 / (6 * h), 2: 1 / (6 * h)}
    assert got.keys() == want.keys()
    assert all(abs(got[o] - want[o]) < 1e-9 for o in want)
    assert sp.smoothed(sp.BACKWARD, 7) == pytest.approx({3: 1 / (7 * h), -4: -1 / (7 * h)})


def test_a_field_built_as_a_moving_average_matches_that_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows(k=3)
    fig = sp.match_figures(_track(rows))
    assert fig["by_window"]["3"] == 0.0
    assert fig["by_window"]["1"] > 0.0 and fig["by_window"]["5"] > 0.0

    def no_division(weights: sp.Weights, k: int) -> sp.Weights:
        half = (k - 1) // 2
        out: sp.Weights = {}
        for j in range(-half, half + 1):
            for o, w in weights.items():
                out[o + j] = out.get(o + j, 0.0) + w
        return out

    monkeypatch.setattr(sp, "smoothed", no_division)
    assert sp.match_figures(_track(rows))["by_window"]["3"] > 0.1


def test_shaw_drops_the_window_around_a_jump_and_its_mutation_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows()
    jump = next(r for r in rows if r["playerId"] == EXAMPLE_PLAYER and r["frameIdx"] == 150)
    jump["x"] = float(jump["x"]) + 1.0 / FT  # one metre in one frame: 25 m/s each way
    jump["speed"] = 13.0 / FT
    fig = sp.match_figures(_track(rows))
    # The backward speed is over 12 at frames 150 and 151, so Shaw's window of 7 loses the rows
    # from 147 to 154.
    assert fig["window_rows"] - fig["shaw_rows"] == 8
    assert fig["over_max"] == 1 and fig["max_speed"] == 13.0

    monkeypatch.setattr(sp, "shaw_rows", lambda t, rows: rows)
    assert sp.match_figures(_track(rows))["shaw_rows"] == fig["window_rows"]


# The public SQL.


def test_the_sql_finds_the_triples_and_no_gap(tmp_path: Path) -> None:
    write_raw(tmp_path / "m", _rows())
    got = sp.run_sql(sp.read_sql(), tmp_path / "m")
    print(f"learn speed synthetic SQL: {got}")
    assert got == (_expected_triples(), 1.0, 0.0)


SQL_MUTATIONS = {
    "no contiguity": (" WHERE f_before = f - 1 AND f_after = f + 1", ""),
    "no partition by player": ("PARTITION BY id ORDER BY f", "ORDER BY f, id"),
}


@pytest.mark.parametrize("name", SQL_MUTATIONS)
def test_each_sql_mutation_changes_the_triples(tmp_path: Path, name: str) -> None:
    write_raw(tmp_path / "m", _rows())
    old, new = SQL_MUTATIONS[name]
    sql = sp.read_sql()
    assert old in sql, f"{name}: {old!r} is no longer in speed.sql"
    got = sp.run_sql(sql.replace(old, new), tmp_path / "m")
    assert got[0] != _expected_triples() or got[2] != 0.0, name


def test_the_sql_names_its_match_once_and_is_lf() -> None:
    raw = sp.SQL_PATH.read_bytes()
    assert raw.count(sp.SQL_MATCH_ID.encode()) == 1
    assert b"\r" not in raw


# The command, on a data root made in tmp_path.


def _root(tmp_path: Path, *, raw: bool) -> Path:
    root = tmp_path / "data"
    write_bronze(root, _rows())
    if raw:
        receipt = root / "raw" / "opendata-basketball"
        receipt.mkdir(parents=True)
        (receipt / "_receipt.json").write_text(json.dumps({"failed": []}), encoding="utf-8")
        write_raw(receipt / "data" / "matches" / str(MATCH), _rows())
    write_possession(tmp_path / "possessions")
    return root


def _run(root: Path, out: Path, *extra: str) -> int:
    return main(
        [
            "learn",
            "speed",
            "--data-dir",
            str(root),
            "--out",
            str(out),
            "--possessions",
            str(root.parent / "possessions"),
            *extra,
        ]
    )


def test_the_file_is_written_lf_and_then_checks_full(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path, raw=True)
    out = tmp_path / "learn" / "speed.json"
    assert _run(root, out) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert b"\r" not in out.read_bytes()
    ex = payload["example"]
    assert ex["frames"] == len(EX_FRAMES) and len(ex["speed"]) == len(EX_FRAMES)
    assert ex["full_precision"]["median_gap"] == 0.0
    assert _run(root, out, "--check") == 0
    assert "FULL 1/1" in capsys.readouterr().out


def test_the_check_is_partial_without_the_raw_files_and_fails_on_a_changed_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path, raw=False)
    out = tmp_path / "speed.json"
    assert _run(root, out) == 0
    assert _run(root, out, "--check") == 0
    assert "PARTIAL 0/1" in capsys.readouterr().out
    out.write_text(
        out.read_text(encoding="utf-8").replace('"r": 1.0', '"r": 0.9'),
        encoding="utf-8",
        newline="\n",
    )
    assert _run(root, out, "--check") == 1
    assert "differs from what bronze gives" in capsys.readouterr().out
