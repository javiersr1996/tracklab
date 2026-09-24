"""`tracklab quality clock` on a fabricated bronze `tracking_frames` /
`tracking_objects` (basketball) and `tracking_frames` (football).

Every step is fabricated to be exact so the check's arithmetic has nothing to
round: `wallClock` advances by exactly 40 ms per native frame except one
engineered jump, and the provider's `speed` is set to a fixed multiple of the
finite-difference speed the check itself computes, so the ratio is exact.
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest

from tracklab.quality import clock
from tracklab.quality.common import report_path
from tracklab.quality.run import run_quality

FPS = 25
DT_MS = 1000 // FPS  # 40


def _values(rows: list[tuple[object, ...]]) -> str:
    return ", ".join(repr(tuple(row)) for row in rows)


def _write(
    data_dir: Path,
    bb_frames: list[tuple[object, ...]],
    bb_objects: list[tuple[object, ...]],
    fb_frames: list[tuple[object, ...]],
) -> None:
    con = duckdb.connect()
    con.execute("CREATE TABLE bb_frames (match_id BIGINT, frameIdx BIGINT, wallClock BIGINT)")
    con.execute(f"INSERT INTO bb_frames VALUES {_values(bb_frames)}")
    bb_path = data_dir / "bronze" / "basketball" / "tracking_frames"
    bb_path.mkdir(parents=True)
    for native in {int(r[0]) for r in bb_frames}:
        con.execute(
            f"COPY (SELECT * FROM bb_frames WHERE match_id = {native}) "
            f"TO '{(bb_path / f'{native}.parquet').as_posix()}'"
        )

    con.execute(
        """
        CREATE TABLE bb_objects (match_id BIGINT, playerId BIGINT, frameIdx BIGINT,
            side VARCHAR, x DOUBLE, y DOUBLE, speed DOUBLE, isDetected BOOLEAN)
        """
    )
    con.execute(f"INSERT INTO bb_objects VALUES {_values(bb_objects)}")
    bb_obj_path = data_dir / "bronze" / "basketball" / "tracking_objects"
    bb_obj_path.mkdir(parents=True)
    for native in {int(r[0]) for r in bb_objects}:
        con.execute(
            f"COPY (SELECT * FROM bb_objects WHERE match_id = {native}) "
            f"TO '{(bb_obj_path / f'{native}.parquet').as_posix()}'"
        )

    con.execute("CREATE TABLE fb_frames (match_id BIGINT, frame BIGINT)")
    fb_path = data_dir / "bronze" / "football" / "tracking_frames"
    fb_path.mkdir(parents=True)
    if fb_frames:
        con.execute(f"INSERT INTO fb_frames VALUES {_values(fb_frames)}")
        for native in {int(r[0]) for r in fb_frames}:
            con.execute(
                f"COPY (SELECT * FROM fb_frames WHERE match_id = {native}) "
                f"TO '{(fb_path / f'{native}.parquet').as_posix()}'"
            )
    else:
        con.execute(f"COPY fb_frames TO '{(fb_path / 'empty.parquet').as_posix()}'")


@pytest.fixture(scope="module")
def report(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[tuple[str, str], tuple[float, int]]:
    root = tmp_path_factory.mktemp("clock")
    # Basketball match 1: 50 frames at exactly 40 ms, one engineered 80 ms jump
    # between frameIdx 10 and 11 (still native-adjacent: frameIdx step is 1).
    bb_frames = [
        (1, f, f * DT_MS if f <= 10 else 10 * DT_MS + DT_MS + (f - 11) * DT_MS + DT_MS)
        for f in range(50)
    ]
    # One player, moving at exactly 5.0 m per frame in x: fd_speed = 5.0 * 25 = 125.0
    # m/s -- above V_MAX (25), so it is dropped, on purpose, and re-added at a
    # in-range speed below.
    bb_objects = [(1, 1, f, "home", 5.0 * f, 0.0, 250.0, True) for f in range(3)]
    # A second player moving at 0.2 m per frame (fd_speed = 0.2*25 = 5.0 m/s, inside
    # (3, 25)); declared speed set to exactly 1.5x that, so the ratio is exact.
    bb_objects += [(1, 2, f, "home", 0.2 * f, 0.0, 1.5 * 5.0, True) for f in range(5)]
    fb_frames = [(2, f) for f in range(30)]
    _write(root / "data", bb_frames, bb_objects, fb_frames)
    reports = root / "reports"
    assert run_quality(["clock"], data_dir=root / "data", reports_dir=reports) == 0
    with report_path(reports, "clock").open(encoding="utf-8", newline="") as handle:
        return {
            (r["match_id"], r["metric"]): (float(r["value"]), int(r["n"]))
            for r in csv.DictReader(handle)
        }


def test_basketball_wallclock_step_and_the_engineered_jump(
    report: dict[tuple[str, str], tuple[float, int]],
) -> None:
    pct, n = report[("bb:1", "clock_step_exact_pct")]
    # 49 native-adjacent pairs, one of them (10 -> 11) is 80 ms instead of 40.
    assert n == 49
    assert pct == pytest.approx(100.0 * 48 / 49, abs=1e-4)


def test_football_step_is_a_pure_contiguity_check(
    report: dict[tuple[str, str], tuple[float, int]],
) -> None:
    # No independent ms field in football: 30 contiguous native frames read 100%.
    assert report[("fb:2", "clock_step_exact_pct")] == (100.0, 29)


def test_basketball_speed_ratio_is_exact_for_the_in_range_player(
    report: dict[tuple[str, str], tuple[float, int]],
) -> None:
    ratio, n = report[("bb:1", "speed_ratio_median")]
    assert ratio == pytest.approx(1.5, abs=1e-9)
    assert n == 4  # player 2's 5 frames give 4 consecutive pairs; player 1's are all out of range
    mismatch, _ = report[("bb:1", "speed_mismatch_pct")]
    assert mismatch == pytest.approx(50.0, abs=1e-4)


def test_no_speed_metrics_for_football(report: dict[tuple[str, str], tuple[float, int]]) -> None:
    assert ("fb:2", "speed_ratio_median") not in report
    assert ("fb:2", "speed_mismatch_pct") not in report


def test_widening_the_speed_gate_admits_the_fast_player(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation: player 1 moves at a constant fd_speed of 125.0 m/s, engineered
    to sit above `V_MAX` (25) so it is excluded. Raising `V_MAX` past 125 admits
    it, and its declared speed (250.0, exactly 2x its fd_speed) then pulls the
    match's ratio away from 1.5 -- proof the gate, not the ratio math, was
    keeping it out."""
    root = tmp_path_factory.mktemp("clock_mutated")
    bb_frames = [(1, f, f * DT_MS) for f in range(10)]
    bb_objects = [(1, 1, f, "home", 5.0 * f, 0.0, 250.0, True) for f in range(3)]
    _write(root / "data", bb_frames, bb_objects, [])
    monkeypatch.setattr(clock, "V_MAX", 200.0)

    results = clock.clock(root / "data", root / "reports")
    by_metric = {r.metric: r.value for r in results if r.match_id == "bb:1"}
    assert by_metric["speed_ratio_median"] == pytest.approx(2.0, abs=1e-9)
