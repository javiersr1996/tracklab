"""`tracklab learn gravity` and the SQL of "Reproduce it" (task 76).

The SQL runs on a match written by hand in `tmp_path`, in the shape of the public bundle (feet,
`wallClock` in ms, 25 fps). Every shot is an exact parabola of g 9.81 and owns a block of frames:

- two clean shots (apex 4.0 m) and `rim_before`, a clean shot with one sample on a rim axis
  before the apex: they are flights;
- `half_frame`: the vertex falls between two frames, so two samples tie for the apex, and the
  ball is tracked only for 21 frames from the first of them: a flight only if the first wins;
- `blocked`: a clean window of a blocked shot, not a flight;
- `no_window`: 15 tracked frames, not a flight;
- `displaced`: apex 6.0 m with one sample after the apex 3 m lower (still above 9.5 ft), a
  residual RMS over 1 ft, not a flight.

So the SQL must give 4 flights and a median of 9.8100. Mutations recorded in tasks/todo.md (each
applied to gravity.sql by hand and run, and also built below, where each must change `flights`):
the apex by the last frame of a tie (the half-frame shot loses its window); the rebound cut also
before the apex (`rim_before` is dropped); no `NOT` on `blocked` (the blocked shot enters); no
RMS filter (the displaced shot enters).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from tracklab.cli import main
from tracklab.learn.gravity import SQL_MATCH_ID, match_sql, read_sql, run_sql

FT = 0.3048
G = 9.81
FPS = 25
BLOCK = 200
RIM_X = (91.86 / 2 - 5.17) * FT
EXPECTED = (4, 9.81)

# kind -> the flight (apex height in m, tracked frames around the apex).
KINDS = ("clean", "clean", "rim_before", "half_frame", "blocked", "no_window", "displaced")


def _samples(kind: str, apex: int) -> dict[int, tuple[float, float, float]]:
    """frame -> (x, y, z) in metres for the tracked frames of one shot."""
    top = 6.0 if kind == "displaced" else 4.0
    vertex = apex + 0.5 if kind == "half_frame" else float(apex)
    frames = range(apex - 30, apex + 31)
    if kind == "half_frame":
        frames = range(apex - 10, apex + 11)
    if kind == "no_window":
        frames = range(apex - 7, apex + 8)
    out = {}
    for f in frames:
        dt = (f - vertex) / FPS
        x = RIM_X if kind == "rim_before" and f == apex - 5 else -3.0 + dt
        z = max(top - 0.5 * G * dt * dt, 0.12)
        if kind == "displaced" and f == apex + 2:
            z -= 3.0
        out[f] = (x, 0.0, z)
    return out


def write_match(folder: Path, match_id: int = int(SQL_MATCH_ID)) -> None:
    """The two files the SQL reads, with the names of the public bundle."""
    folder.mkdir(parents=True, exist_ok=True)
    shots, ball = [], {}
    for k, kind in enumerate(KINDS):
        apex = k * BLOCK + 100
        shots.append(
            {
                "id": f"shot-{match_id}-{k}",
                "startFrame": apex - 15,
                "endFrame": apex + 10,
                "blocked": kind == "blocked",
            }
        )
        ball.update(_samples(kind, apex))
    shots.append({"id": "no-start", "startFrame": None, "endFrame": None, "blocked": False})
    (folder / f"{match_id}_dynamic_events.json").write_text(
        json.dumps({"shots": shots}), encoding="utf-8", newline="\n"
    )
    lines = [
        json.dumps(
            {
                "frameIdx": f,
                "wallClock": f * 1000 // FPS,
                "ball": {"xyz": [x / FT, y / FT, z / FT]},
            }
        )
        for f, (x, y, z) in sorted(ball.items())
    ]
    with gzip.open(folder / f"{match_id}_tracking_data.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


@pytest.fixture
def match(tmp_path: Path) -> Path:
    folder = tmp_path / "match"
    write_match(folder)
    return folder


def test_the_sql_reproduces_the_hand_made_flights(match: Path) -> None:
    got = run_sql(read_sql(), match)
    print(f"learn gravity synthetic: flights={got[0]} g_median={got[1]}")
    assert got == EXPECTED


MUTATIONS = {
    "last apex of a tie": ("ORDER BY z DESC, f)", "ORDER BY z DESC, f DESC)"),
    "rebound before the apex": ("bool_or(k > 0 AND (", "bool_or(true AND ("),
    "blocked shots enter": (" AND NOT coalesce(s.blocked, false)", ""),
    "no residual filter": (" WHERE rms < 0.3048", ""),
}


@pytest.mark.parametrize("name", MUTATIONS)
def test_each_mutation_changes_the_flights(match: Path, name: str) -> None:
    old, new = MUTATIONS[name]
    sql = read_sql()
    assert old in sql, f"{name}: {old!r} is no longer in gravity.sql"
    flights, _ = run_sql(sql.replace(old, new), match)
    assert flights != EXPECTED[0], f"{name}: the hand-made match cannot tell it apart"


def test_the_match_id_is_named_exactly_twice_and_the_file_is_lf() -> None:
    raw = (Path(__file__).parents[2] / "src" / "tracklab" / "learn" / "gravity.sql").read_bytes()
    assert raw.count(SQL_MATCH_ID.encode()) == 2
    assert b"\r" not in raw
    assert match_sql(191313).count("191313") == 2


# The command, on a data root made in tmp_path.


def _data_root(tmp_path: Path, ids: list[int]) -> Path:
    root = tmp_path / "data"
    raw = root / "raw" / "opendata-basketball"
    raw.mkdir(parents=True)
    (raw / "_receipt.json").write_text(json.dumps({"failed": []}), encoding="utf-8")
    for i in ids:
        write_match(raw / "data" / "matches" / str(i), i)
    return root


def _quality(tmp_path: Path, rows: dict[int, tuple[int, float]]) -> Path:
    gravity = []
    for i, (flights, g) in rows.items():
        gravity.append(
            {"sport": "basketball", "match_id": f"bb:{i}", "metric": "flights", "value": flights}
        )
        gravity.append(
            {"sport": "basketball", "match_id": f"bb:{i}", "metric": "g_median", "value": g}
        )
    gravity.append({"sport": "football", "match_id": "fb:1", "metric": "flights", "value": 3})
    path = tmp_path / "quality.json"
    path.write_text(json.dumps({"checks": {"gravity": gravity}}), encoding="utf-8")
    return path


def _check(root: Path, quality: Path) -> int:
    return main(["learn", "gravity", "--check", "--data-dir", str(root), "--quality", str(quality)])


def test_check_is_full_when_every_match_is_recomputed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _data_root(tmp_path, [11, 22])
    assert _check(root, _quality(tmp_path, {11: EXPECTED, 22: EXPECTED})) == 0
    assert "FULL 2/2" in capsys.readouterr().out


def test_check_is_partial_without_the_raw_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _data_root(tmp_path, [11])
    assert _check(root, _quality(tmp_path, {11: EXPECTED, 22: EXPECTED})) == 0
    assert "PARTIAL 1/2" in capsys.readouterr().out
    assert _check(tmp_path / "nowhere", _quality(tmp_path, {11: EXPECTED})) == 0
    assert "PARTIAL 0/1" in capsys.readouterr().out


def test_check_fails_when_a_figure_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _data_root(tmp_path, [11])
    assert _check(root, _quality(tmp_path, {11: (5, 9.81)})) == 1
    assert _check(root, _quality(tmp_path, {11: (4, 9.8)})) == 1
    assert "DIFFERENT" in capsys.readouterr().out
