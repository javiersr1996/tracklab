"""`tracklab fixtures` on a fabricated bronze, plus the size of the versioned slice.

The fabricated bronze has what the real one only has by accident: rows of a
second match, rows either side of the window, a chance player whose chance is
outside it, and a season aggregate that must go whole.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from tracklab.fixtures import Cut, cut_fixtures

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "data"
MAX_BYTES = 3 * 1024 * 1024


def _write(bronze: Path, sport: str, table: str, name: str, sql: str) -> None:
    path = bronze / sport / table
    path.mkdir(parents=True, exist_ok=True)
    duckdb.connect().execute(f"COPY ({sql}) TO '{(path / name).as_posix()}' (FORMAT PARQUET)")


def _rows(path: Path, sql: str = "SELECT * FROM t ORDER BY ALL") -> list[tuple[object, ...]]:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{path.as_posix()}')")
    return [tuple(r) for r in con.execute(sql).fetchall()]


def _bronze(root: Path) -> Path:
    bronze = root / "bronze"
    frames = "SELECT 7 AS match_id, range AS frameIdx FROM range(0, 100)"
    _write(bronze, "basketball", "tracking_frames", "7.parquet", frames)
    _write(bronze, "basketball", "tracking_frames", "8.parquet", frames.replace("7 AS", "8 AS"))
    _write(
        bronze,
        "basketball",
        "events_chances",
        "7.parquet",
        "SELECT 7 AS match_id, * FROM (VALUES ('c-in', 20), ('c-out', 90)) v(id, startFrame)",
    )
    _write(
        bronze,
        "basketball",
        "events_chance_players",
        "7.parquet",
        "SELECT 7 AS match_id, * FROM (VALUES ('c-in', 1), ('c-out', 2)) v(chanceId, playerId)",
    )
    _write(bronze, "basketball", "player_id_aliases", "data.parquet", "SELECT 1 AS player_id")
    _write(
        bronze, "basketball", "aggregates_shots", "data.parquet", "SELECT 1 AS n UNION ALL SELECT 2"
    )
    _write(
        bronze,
        "common",
        "orientation",
        "data.parquet",
        "SELECT * FROM (VALUES (7, 1), (8, 1)) v(native_match_id, period)",
    )
    return root


def test_the_cut_keeps_one_match_and_the_rows_that_start_in_the_window(tmp_path: Path) -> None:
    data = _bronze(tmp_path / "data")
    out = tmp_path / "out"
    cut_fixtures(data, out, (Cut("basketball", 7, 10, 30),))
    bronze = out / "bronze" / "basketball"

    frames = _rows(
        bronze / "tracking_frames" / "7.parquet",
        "SELECT min(frameIdx), max(frameIdx), count(*) FROM t",
    )
    assert frames == [(10, 30, 21)]
    assert not (bronze / "tracking_frames" / "8.parquet").exists()
    assert _rows(bronze / "events_chances" / "7.parquet", "SELECT id FROM t") == [("c-in",)]


def test_a_chance_player_follows_its_chance(tmp_path: Path) -> None:
    data = _bronze(tmp_path / "data")
    out = tmp_path / "out"
    cut_fixtures(data, out, (Cut("basketball", 7, 10, 30),))
    players = out / "bronze" / "basketball" / "events_chance_players" / "7.parquet"
    assert _rows(players, "SELECT chanceId FROM t") == [("c-in",)]


def test_season_tables_and_aggregates_go_whole(tmp_path: Path) -> None:
    data = _bronze(tmp_path / "data")
    out = tmp_path / "out"
    cut_fixtures(data, out, (Cut("basketball", 7, 10, 30),))
    bronze = out / "bronze"
    assert _rows(bronze / "basketball" / "player_id_aliases" / "data.parquet") == [(1,)]
    shots = bronze / "basketball" / "aggregates_shots" / "data.parquet"
    assert _rows(shots) == [(1,), (2,)]
    orientation = _rows(bronze / "common" / "orientation" / "data.parquet")
    assert orientation == [(7, 1)]


def test_the_versioned_slice_holds_both_sports_under_three_megabytes() -> None:
    files = [p for p in (FIXTURES / "bronze").rglob("*.parquet")]
    size = sum(p.stat().st_size for p in files)
    sports = {p.relative_to(FIXTURES / "bronze").parts[0] for p in files}
    print(f"{len(files)} files, {size} bytes")
    assert sports == {"basketball", "football", "common"}
    assert size < MAX_BYTES
