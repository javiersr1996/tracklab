"""`tracklab learn pass` and the SQL of lesson 7's "Reproduce it".

A synthetic match in feet, like the public bundle. Passer and receiver stand 8 m apart at every
pass's start, so `distance` is 8 m; the ball leaves 1 m from the passer and arrives 1 m from the
receiver:

- P1, frames 100 to 110 (0.4 s): the ball flies level, 6 m in a line: chord 6 m, path 6 m,
  15 m/s, `distance` over the time 20 m/s, chord over `distance` 0.75;
- P2, frames 200 to 212 (0.48 s): a bounce pass, down to the floor and up again over the same
  6 m: chord 6 m, path longer, 12.5 m/s;
- P3 ends where it starts; P4 misses the ball at one frame; P5 is not complete; P6 has no
  `distance`. None of the four is measured.

So complete 4 (P1 to P4), forward 3, n 2. Mutations (a test that cannot fail protects nothing):
the chord in feet (`M_PER_FT` at 1), the time at 30 fps, and on the SQL: passes that end where
they start, the chord from the players' `distance`, a path over every frame pair whatever the
gap. Including passes that end where they start in Python was run by hand: P3 divides by zero.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import pytest

from tracklab.cli import main
from tracklab.learn import passes as ps

FT = 0.3048
MATCH = int(ps.SQL_MATCH_ID)
PASSER, RECEIVER = 1, 2


def _ball(name: str, k: int) -> tuple[float, float, float] | None:
    """The ball (m) k frames into a pass."""
    if name == "P1":
        return (1.0 + 0.6 * k, 0.0, 1.5)
    if name == "P2":  # down to the floor at k = 6, back up by k = 12
        return (1.0 + 0.5 * k, 0.0, abs(6 - k) / 6)
    if name == "P4" and k == 3:
        return None
    return (1.0 + 0.6 * k, 0.0, 1.5)


PASSES: dict[str, dict[str, Any]] = {
    "P1": {"f0": 100, "f1": 110, "complete": True, "distance": 8.0},
    "P2": {"f0": 200, "f1": 212, "complete": True, "distance": 8.0},
    "P3": {"f0": 300, "f1": 300, "complete": True, "distance": 8.0},
    "P4": {"f0": 400, "f1": 410, "complete": True, "distance": 8.0},
    "P5": {"f0": 500, "f1": 510, "complete": False, "distance": 8.0},
    "P6": {"f0": 600, "f1": 610, "complete": True, "distance": None},
}


def _objects() -> list[tuple[int, str, int | None, float, float, float | None]]:
    """(frame, side, player, x ft, y ft, z ft) for every pass's frames."""
    rows = []
    for name, p in PASSES.items():
        for f in range(p["f0"], p["f1"] + 1):
            rows.append((f, "home", PASSER, 0.0, 0.0, 0.0))
            rows.append((f, "home", RECEIVER, 8.0 / FT, 0.0, 0.0))
            ball = _ball(name, f - p["f0"])
            if ball is not None:
                rows.append((f, "ball", None, ball[0] / FT, ball[1] / FT, ball[2] / FT))
    return rows


def write_bronze(root: Path) -> None:
    bronze = root / "bronze" / "basketball"
    for table in ("events_passes", "tracking_objects"):
        (bronze / table).mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE p (id VARCHAR, startFrame BIGINT, endFrame BIGINT, complete BOOLEAN, "
        "distance DOUBLE, passerId BIGINT, receiverId BIGINT)"
    )
    for name, p in PASSES.items():
        d = None if p["distance"] is None else p["distance"] / FT
        con.execute(
            "INSERT INTO p VALUES (?, ?, ?, ?, ?, ?, ?)",
            [name, p["f0"], p["f1"], p["complete"], d, PASSER, RECEIVER],
        )
    con.execute(
        "CREATE TABLE o (frameIdx BIGINT, side VARCHAR, playerId BIGINT, x DOUBLE, y DOUBLE, "
        "z DOUBLE)"
    )
    con.executemany("INSERT INTO o VALUES (?, ?, ?, ?, ?, ?)", _objects())
    for name, table in (("events_passes", "p"), ("tracking_objects", "o")):
        path = (bronze / name / f"{MATCH}.parquet").as_posix()
        con.execute(f"COPY {table} TO '{path}' (FORMAT parquet)")


def write_raw(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    events = {
        "passes": [
            {
                "id": name,
                "startFrame": p["f0"],
                "endFrame": p["f1"],
                "complete": p["complete"],
                "distance": None if p["distance"] is None else p["distance"] / FT,
            }
            for name, p in PASSES.items()
        ]
    }
    (folder / f"{MATCH}_dynamic_events.json").write_text(json.dumps(events), encoding="utf-8")
    by_frame: dict[int, dict[str, Any]] = {}
    for f, side, _, x, y, z in _objects():
        frame = by_frame.setdefault(f, {"frameIdx": f, "ball": {}})
        if side == "ball":
            frame["ball"] = {"xyz": [x, y, z]}
    with gzip.open(folder / f"{MATCH}_tracking_data.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(v) for _, v in sorted(by_frame.items())) + "\n")


def _figures(root: Path) -> dict[str, Any]:
    return ps.read_match(root / "bronze" / "basketball", MATCH)


def _bounce_path() -> float:
    points = [_ball("P2", k) for k in range(13)]
    return sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False))  # type: ignore[arg-type]


def test_the_selection_and_the_figures(tmp_path: Path) -> None:
    write_bronze(tmp_path)
    fig = _figures(tmp_path)
    print(f"learn pass synthetic: {fig}")
    assert (fig["complete"], fig["forward"], fig["n"]) == (4, 3, 2)
    assert fig["chord_speed_median"] == round((15.0 + 12.5) / 2, 2)
    assert fig["distance_speed_median"] == round((20.0 + 8.0 / 0.48) / 2, 2)
    assert fig["path_over_chord"] == round((1.0 + _bounce_path() / 6.0) / 2, 4)
    assert fig["chord_over_distance"] == 0.75
    assert (fig["separation_n"], fig["separation_gap_max"]) == (2, 0.0)


def test_mutation_chord_in_feet_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_bronze(tmp_path)
    monkeypatch.setattr(ps, "M_PER_FT", 1.0)
    assert _figures(tmp_path)["chord_speed_median"] != round((15.0 + 12.5) / 2, 2)


def test_mutation_frame_rate_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_bronze(tmp_path)
    monkeypatch.setattr(ps, "FPS", 30)
    assert _figures(tmp_path)["chord_speed_median"] != round((15.0 + 12.5) / 2, 2)


# The public SQL.


def test_the_sql_gives_the_figures_of_the_python(tmp_path: Path) -> None:
    write_raw(tmp_path / "m")
    write_bronze(tmp_path)
    got = ps.run_sql(ps.read_sql(), tmp_path / "m")
    fig = _figures(tmp_path)
    print(f"learn pass synthetic SQL: {got}")
    assert got == tuple(fig[k] for k in ps.SQL_FIELDS)


SQL_MUTATIONS: dict[str, list[tuple[str, str]]] = {
    "passes that end where they start": [
        ("AND p.endFrame > p.startFrame", "AND p.endFrame >= p.startFrame"),
        ("any_value(f1 - f0) / 25 AS s", "greatest(any_value(f1 - f0), 1) / 25 AS s"),
    ],
    "the chord from the players' distance": [("chord / s, 0.5)", "d / s, 0.5)")],
    "a path over any gap": [
        ("LEFT JOIN ball a ON a.f = b.f - 1", "LEFT JOIN ball a ON a.f = b.f - 2"),
    ],
}


@pytest.mark.parametrize("name", SQL_MUTATIONS)
def test_each_sql_mutation_changes_a_figure(tmp_path: Path, name: str) -> None:
    write_raw(tmp_path / "m")
    write_bronze(tmp_path)
    sql = ps.read_sql()
    for old, new in SQL_MUTATIONS[name]:
        assert old in sql, f"{name}: {old!r} is no longer in pass.sql"
        sql = sql.replace(old, new)
    want = tuple(_figures(tmp_path)[k] for k in ps.SQL_FIELDS)
    assert ps.run_sql(sql, tmp_path / "m") != want, name


def test_the_sql_names_its_match_in_its_file_names_and_is_lf() -> None:
    raw = ps.SQL_PATH.read_bytes()
    assert raw.count(ps.SQL_MATCH_ID.encode()) == ps.SQL_NAMES
    assert b"\r" not in raw


# The example and the command, on a data root made in tmp_path.

STEM = f"bb_possessions_possession-{MATCH}-1-1.json"


def write_possession(folder: Path) -> None:
    """A published possession over frames 95 to 215: P1 and P2 inside it, positions in metres."""
    folder.mkdir(parents=True, exist_ok=True)
    rows: dict[int, list[list[Any]]] = {}
    for f, side, player, x, y, z in _objects():
        if not 95 <= f <= 215:
            continue
        i = 2 if side == "ball" else (player or 0) - 1
        zz = None if z is None or side != "ball" else round(z * FT, 2)
        rows.setdefault(f, []).append([i, round(x * FT, 2), round(y * FT, 2), zz, 1])
    frames = [{"t": 40 * f, "clock": 0.0, "o": rows.get(f, [])} for f in range(95, 216)]
    entities = [
        {"i": 0, "entity_id": f"bb:{PASSER}", "kind": "player"},
        {"i": 1, "entity_id": f"bb:{RECEIVER}", "kind": "player"},
        {"i": 2, "entity_id": "bb:ball", "kind": "ball"},
    ]
    pos = {"match": {"match_id": f"bb:{MATCH}"}, "entities": entities, "frames": frames}
    (folder / STEM).write_text(json.dumps(pos), encoding="utf-8")


def test_the_example_is_every_measured_pass_of_the_possession(tmp_path: Path) -> None:
    write_bronze(tmp_path)
    write_possession(tmp_path / "possessions")
    ex = ps.example_figures(tmp_path / "bronze" / "basketball", tmp_path / "possessions" / STEM)
    assert [p["pass_id"] for p in ex["passes"]] == ["P1", "P2"]
    assert ex["passes"][0]["chord_speed"] == 15.0
    assert ex["passes"][1]["path_m"] > ex["passes"][1]["chord_m"]
    assert (ex["passes"][0]["passer"], ex["passes"][0]["receiver"]) == (0, 1)


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
    args = ["learn", "pass", "--data-dir", str(root), "--out", str(out)]
    return main([*args, "--possessions", str(root.parent / "possessions"), *extra])


def test_the_file_is_written_lf_and_then_checks_full(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ps, "EXAMPLE_FILE", STEM)
    root = _root(tmp_path, raw=True)
    out = tmp_path / "learn" / "pass.json"
    assert _run(root, out) == 0
    assert b"\r" not in out.read_bytes()
    assert _run(root, out, "--check") == 0
    assert "FULL 1/1" in capsys.readouterr().out


def test_the_check_is_partial_without_the_raw_files_and_fails_on_a_changed_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ps, "EXAMPLE_FILE", STEM)
    root = _root(tmp_path, raw=False)
    out = tmp_path / "pass.json"
    assert _run(root, out) == 0
    assert _run(root, out, "--check") == 0
    assert "PARTIAL 0/1" in capsys.readouterr().out
    out.write_text(
        out.read_text(encoding="utf-8").replace('"n": 2,', '"n": 3,'),
        encoding="utf-8",
        newline="\n",
    )
    assert _run(root, out, "--check") == 1
    assert "differs from what bronze gives" in capsys.readouterr().out
