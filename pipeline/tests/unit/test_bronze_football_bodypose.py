"""Bronze football body pose and its coverage on a fabricated zip (task 58). No real data.

The zip has the shapes of the real members that the 309-frame sample lacks: a frame outside
every period (nulls, no players), a player who is listed but has no pose (`joints: null`), a
`__MACOSX` resource fork beside the member, joint keys in a shuffled order, a frame number that
jumps, and a timestamp that disagrees with the period. The counts are written down by hand below
and read back by DuckDB, a second reader that shares no line with the writer.
"""

from __future__ import annotations

import json
import random
import zipfile
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq
import pytest

from tracklab.bronze.common import bronze_path
from tracklab.bronze.football.bodypose import (
    BODYPOSE_FRAMES,
    BODYPOSE_PLAYERS,
    TABLES,
    build_bodypose_match,
)
from tracklab.cli import BRONZE_BUILDERS, BRONZE_SOURCE_IDS, bronze_source_id
from tracklab.dagster_defs.assets_bronze import BRONZE_TABLES
from tracklab.fixtures import POSE_FALLBACK_FRAMES
from tracklab.ingest.manifest import FileEntry
from tracklab.pose import coverage
from tracklab.pose.coverage import coverage_match, run_pose_coverage
from tracklab.pose.jsonl import JOINTS

MATCH = 8100001
A, B, C = 501, 502, 503
NULL_BALL: dict[str, Any] = {"x": None, "y": None, "z": None, "is_detected": None}
NO_POSSESSION: dict[str, Any] = {"player_id": None, "group": None}
LAST_MAE = 5.0 + len(JOINTS) - 1


def joints(seed: float) -> dict[str, Any]:
    """Every joint with values that name it: x = index in JOINTS + seed, z = 0.1 * index."""
    out = {
        name: {"xyz": [i + seed, 0.5 + seed, 0.1 * i], "p90_mae_cm": 5.0 + i}
        for i, name in enumerate(JOINTS)
    }
    keys = list(out)
    random.Random(int(seed * 10000)).shuffle(keys)
    return {k: out[k] for k in keys}


def player(pid: int, posed: bool, detected: bool = True) -> dict[str, Any]:
    return {
        "player_id": pid,
        "x": 10.0 + pid,
        "y": -3.0,
        "is_detected": detected,
        "joints": joints(pid / 1000) if posed else None,
    }


def line(
    frame: int,
    period: int | None,
    timestamp: str | None,
    players: list[dict[str, Any]],
    ball: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        {
            "frame": frame,
            "timestamp": timestamp,
            "period": period,
            "ball_data": NULL_BALL if ball is None else ball,
            "possession": NO_POSSESSION,
            "image_corners_projection": {},
            "player_data": players,
        }
    )


BALL = {"x": 1.0, "y": 2.0, "z": 0.3, "is_detected": None}  # position kept, is_detected null
LINES = [
    line(0, None, None, []),
    line(1, 1, "00:00:00.04", [player(A, True), player(B, False, False), player(C, True)], BALL),
    line(2, 1, "00:46:10.08", [player(A, True), player(B, False, False), player(C, False)], BALL),
    # Frame 2 is stoppage time of period 1 (the clock is past 45:00); frame 124487 opens period 2.
    line(124487, 2, "00:49:47.48", [player(A, True, False), player(B, False), player(C, False)]),
]


def make_zip(path: Path, lines: list[str]) -> FileEntry:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{MATCH}.jsonl", "\n".join(lines) + "\n")
        archive.writestr(f"__MACOSX/._{MATCH}.jsonl", b"\x00\x05\x16\x07 not json")
    size = path.stat().st_size
    return FileEntry(f"raw/{MATCH}.jsonl.zip", size, "0" * 64, True, "bodypose_zip", MATCH)


@pytest.fixture
def built(tmp_path: Path) -> Path:
    raw, data = tmp_path / "raw", tmp_path / "data"
    entry = make_zip(raw / "raw" / f"{MATCH}.jsonl.zip", LINES)
    build_bodypose_match(entry, raw, data, "c" * 40)
    return data


def rows(data: Path, table: str, sql: str) -> list[tuple[Any, ...]]:
    path = bronze_path(data, "football", table, MATCH).as_posix()
    return duckdb.connect().execute(sql.format(t=f"read_parquet('{path}')")).fetchall()


def test_the_files_have_the_declared_schemas(built: Path) -> None:
    for table, declared in TABLES.items():
        path = bronze_path(built, "football", table, MATCH)
        assert pq.read_schema(path).equals(declared, check_metadata=False), table


def test_only_the_parquet_files_appear_under_the_data_root(built: Path, tmp_path: Path) -> None:
    """The member is read from the zip as a stream: nothing is extracted next to the Parquet."""
    names = sorted(p.name for p in built.rglob("*") if p.is_file())
    assert names == [f"{MATCH}.parquet", f"{MATCH}.parquet"]
    assert not list(tmp_path.rglob("*.jsonl")) and not list(tmp_path.rglob("*.tmp"))


def test_the_denominator_counts_every_listed_player_and_the_rows_only_those_with_pose(
    built: Path,
) -> None:
    sql = "select frame, n_players, n_with_pose from {t} order by frame"
    assert rows(built, "bodypose_frames", sql) == [(0, 0, 0), (1, 3, 2), (2, 3, 1), (124487, 3, 1)]
    sql = "select frame, player_id from {t} order by frame, player_id"
    assert rows(built, "bodypose_players", sql) == [(1, A), (1, C), (2, A), (124487, A)]


def test_the_period_is_the_field_and_the_outside_frame_is_a_row_with_nulls(built: Path) -> None:
    sql = "select frame, period, timestamp, ball_x from {t} order by frame"
    assert rows(built, "bodypose_frames", sql) == [
        (0, None, None, None),
        (1, 1, "00:00:00.04", 1.0),
        (2, 1, "00:46:10.08", 1.0),
        (124487, 2, "00:49:47.48", None),
    ]
    sql = "select ball_is_detected from {t} where frame = 1"
    assert rows(built, "bodypose_frames", sql) == [(None,)]


def test_joints_are_in_the_order_of_JOINTS_whatever_the_order_of_the_keys(built: Path) -> None:
    sql = f"select joints, mae from {{t}} where frame = 1 and player_id = {A}"
    ((flat, mae),) = rows(built, "bodypose_players", sql)
    for i in range(len(JOINTS)):
        expected = [i + A / 1000, 0.5 + A / 1000, 0.1 * i]
        assert flat[3 * i : 3 * i + 3] == pytest.approx(expected, abs=1e-5)
        assert mae[i] == pytest.approx(5.0 + i)


def test_the_coverage_of_the_fabricated_match(built: Path) -> None:
    m = coverage_match(built, MATCH)
    assert m is not None
    periods = m["periods"]
    counts = {
        k: (v["frames"], v["frames_with_pose"], v["player_frames"], v["with_pose"])
        for k, v in periods.items()
    }
    assert counts == {
        "1": (2, 2, 6, 3),
        "2": (1, 1, 3, 1),
        "outside": (1, 0, 0, 0),
        "total": (4, 3, 9, 4),
    }
    assert periods["total"]["joint_observations"] == 4 * len(JOINTS)
    assert periods["total"]["with_pose_detected"] == 3  # A has a pose in period 2, undetected
    by_player = {p["player_id"]: p for p in m["players"]}
    a = by_player[A]
    assert (a["frames_present"], a["with_pose"], a["longest_run"]) == (3, 3, 2)
    assert (by_player[B]["with_pose"], by_player[B]["longest_run"]) == (0, 0)
    assert by_player[C]["longest_run"] == 1
    assert m["common_run_lengths"] == [{"length": 1, "count": 2}, {"length": 2, "count": 1}]
    assert (m["mae_cm"]["all"]["min"], m["mae_cm"]["all"]["max"]) == (5.0, LAST_MAE)
    assert m["z_m"] == {"min": 0.0, "max": pytest.approx(0.1 * (len(JOINTS) - 1), abs=1e-4)}


def test_a_slice_cannot_be_recounted(built: Path, tmp_path: Path) -> None:
    """A bronze cut by `tracklab fixtures` does not start at line 0: no coverage is invented."""
    cut = tmp_path / "cut"
    for table in TABLES:
        source = bronze_path(built, "football", table, MATCH).as_posix()
        target = bronze_path(cut, "football", table, MATCH)
        target.parent.mkdir(parents=True)
        duckdb.connect().execute(
            f"copy (select * from read_parquet('{source}') where source_row >= 1) "
            f"to '{target.as_posix()}' (format parquet)"
        )
    assert coverage_match(cut, MATCH) is None


def test_check_is_full_on_the_whole_bronze_and_partial_on_a_slice(
    built: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = tmp_path / "reports"
    monkeypatch.setattr(coverage, "match_ids", lambda _path: [MATCH, MATCH + 1])
    assert run_pose_coverage(built, reports) == 1  # one match has no bronze: nothing written
    assert not reports.exists()
    monkeypatch.setattr(coverage, "match_ids", lambda _path: [MATCH])
    assert run_pose_coverage(built, reports) == 0
    assert "FULL 1/1" in capsys.readouterr().out
    assert run_pose_coverage(built, reports, check=True) == 0
    assert "FULL 1/1" in capsys.readouterr().out
    target = reports / "pose_coverage.json"
    report = json.loads(target.read_text(encoding="utf-8"))
    report["matches"][str(MATCH)]["periods"]["total"]["with_pose"] += 1
    target.write_text(json.dumps(report), encoding="utf-8")
    assert run_pose_coverage(built, reports, check=True) == 1
    target.write_text(json.dumps({"matches": {str(MATCH): {}}}), encoding="utf-8")
    assert run_pose_coverage(tmp_path / "empty", reports, check=True) == 0
    assert "PARTIAL 0/1" in capsys.readouterr().out


def test_the_bodypose_group_is_registered_on_its_own_source() -> None:
    assert ("football", "bodypose") in BRONZE_BUILDERS
    assert ("football", "bodypose") in BRONZE_SOURCE_IDS
    assert bronze_source_id("football", "bodypose") == "opendata-bodypose"
    assert bronze_source_id("football", "tracking") == "opendata-football"


def test_the_asset_tables_are_the_builders_tables() -> None:
    assert set(BRONZE_TABLES[("football", "bodypose")]) == set(TABLES)
    assert BODYPOSE_PLAYERS.names[:4] == BODYPOSE_FRAMES.names[:4]


def test_two_builds_write_the_same_bytes(built: Path, tmp_path: Path) -> None:
    raw, again = tmp_path / "r2", tmp_path / "again"
    entry = make_zip(raw / "raw" / f"{MATCH}.jsonl.zip", LINES)
    build_bodypose_match(entry, raw, again, "c" * 40)
    for table in TABLES:
        one = bronze_path(built, "football", table, MATCH).read_bytes()
        two = bronze_path(again, "football", table, MATCH).read_bytes()
        assert one == two, table


def test_a_member_that_is_not_the_pose_format_fails_with_its_line(tmp_path: Path) -> None:
    bad = json.loads(LINES[1])
    del bad["player_data"][0]["joints"]["nose"]
    entry = make_zip(tmp_path / "raw" / "raw" / f"{MATCH}.jsonl.zip", [LINES[0], json.dumps(bad)])
    with pytest.raises(ValueError, match="line 1"):
        build_bodypose_match(entry, tmp_path / "raw", tmp_path / "data", "c" * 40)
    assert not list((tmp_path / "data").rglob("*.parquet"))


def test_the_versioned_fixture_is_a_slice_the_coverage_refuses_to_recount() -> None:
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "data"
    path = bronze_path(fixtures, "football", "bodypose_frames", 1925299).as_posix()
    n, first = duckdb.connect().execute(
        "select count(*), min(source_row) from read_parquet(?)", [path]
    ).fetchone() or (0, 0)
    assert (n, first > 0) == (POSE_FALLBACK_FRAMES, True)
    assert coverage_match(fixtures, 1925299) is None


def test_a_stretch_of_consecutive_frames_never_crosses_a_period(tmp_path: Path) -> None:
    lines = [
        line(10, 1, "00:45:00.00", [player(A, True)]),
        line(11, 2, "00:45:00.04", [player(A, True)]),
        line(12, 2, "00:45:00.08", [player(A, True)]),
    ]
    raw, data = tmp_path / "raw", tmp_path / "data"
    build_bodypose_match(make_zip(raw / "raw" / f"{MATCH}.jsonl.zip", lines), raw, data, "c" * 40)
    m = coverage_match(data, MATCH)
    assert m is not None
    assert m["players"][0]["longest_run"] == 2
    assert m["common_run_lengths"] == [{"length": 1, "count": 1}, {"length": 2, "count": 1}]
