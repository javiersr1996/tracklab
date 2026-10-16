"""`tracklab fixtures` on a fabricated bronze, plus the size of the versioned slice.

The fabricated bronze has what the real one only has by accident: rows of a
second match, rows either side of the window, a chance player whose chance is
outside it, and a season aggregate that must go whole.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

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


def _pose_bronze(root: Path, pose_matches: tuple[int, ...] = (30, 9, 1925299, 1996435)) -> Path:
    """Football with a tracking match (7) and pose matches (by default 30, 9 and P6's two, each
    a made-up table); pose starts at frame 200."""
    bronze = root / "bronze"
    _write(
        bronze,
        "football",
        "tracking_frames",
        "7.parquet",
        "SELECT 7 AS match_id, range AS frame FROM range(0, 100)",
    )
    for match in pose_matches:
        # 400 pose frames; the first 200 are outside the periods (no pose), the rest have one.
        frames = (
            f"SELECT {match} AS match_id, range AS frame, "
            "CASE WHEN range < 200 THEN 0 ELSE 1 END AS n_with_pose FROM range(0, 400)"
        )
        _write(bronze, "football", "bodypose_frames", f"{match}.parquet", frames)
        players = f"SELECT {match} AS match_id, range AS frame FROM range(200, 400)"
        _write(bronze, "football", "bodypose_players", f"{match}.parquet", players)
    _write(bronze, "common", "orientation", "data.parquet", "SELECT 7 AS native_match_id, 30 AS m")
    return root


def test_pose_tables_of_a_match_without_pose_are_the_first_frames_with_pose_of_1925299(
    tmp_path: Path,
) -> None:
    """The fallback is P6's calibration match, never the lowest id (9 here) and never 1996435."""
    data = _pose_bronze(tmp_path / "data")
    out = tmp_path / "out"
    cut_fixtures(data, out, (Cut("football", 7, 10, 30),))
    pose = out / "bronze" / "football"
    for table in ("bodypose_frames", "bodypose_players"):
        got = _rows(
            pose / table / "1925299.parquet", "SELECT min(frame), max(frame), count(*) FROM t"
        )
        assert got == [(200, 249, 50)], table
        assert sorted(p.name for p in (pose / table).iterdir()) == ["1925299.parquet"]


def test_pose_tables_without_1925299_fail_rather_than_fall_back_on_another_match(
    tmp_path: Path,
) -> None:
    data = _pose_bronze(tmp_path / "data", pose_matches=(9, 1996435))
    with pytest.raises(FileNotFoundError, match="1925299"):
        cut_fixtures(data, tmp_path / "out", (Cut("football", 7, 10, 30),))
    assert not (tmp_path / "out" / "bronze" / "football" / "bodypose_frames").exists()


def test_pose_tables_of_a_match_with_pose_follow_the_window_in_pose_frames(tmp_path: Path) -> None:
    data = _pose_bronze(tmp_path / "data")
    out = tmp_path / "out"
    # Tracking frames 90..100 are pose frames 225..250; the cut's match is 30.
    cut_fixtures(data, out, (Cut("football", 30, 90, 100),))
    pose = out / "bronze" / "football"
    got = _rows(pose / "bodypose_players" / "30.parquet", "SELECT min(frame), max(frame) FROM t")
    assert got == [(225, 250)]
    assert not (pose / "bodypose_players" / "9.parquet").exists()


def test_the_pose_cut_opens_only_the_file_of_its_match(tmp_path: Path) -> None:
    """1996435's file replaced by bytes that are no Parquet: the cut of 1925299 reads its own
    file alone (task 60, phase B2), so it never touches 1996435's and still succeeds."""
    data = _pose_bronze(tmp_path / "data")
    for table in ("bodypose_frames", "bodypose_players"):
        (data / "bronze" / "football" / table / "1996435.parquet").write_bytes(b"not a parquet")
    out = tmp_path / "out"
    cut_fixtures(data, out, (Cut("football", 7, 10, 30),))
    players = out / "bronze" / "football" / "bodypose_players" / "1925299.parquet"
    assert _rows(players, "SELECT count(*) FROM t") == [(50,)]
