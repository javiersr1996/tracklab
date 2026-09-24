"""`tracklab quality entry_angle` on a fabricated `frames` and bronze `events_shots`.

One match has a made shot whose horizontal flight is engineered so every number
is exact: the ball falls at a constant rate near the arrival frame (so the
straight-line fit that stands in for "the angle the bundle's z reports" recovers
that rate with zero residual), and the required angle is computed by hand with
the same formula the module docstring states. A second match has too few ball
frames after the shot starts for a `SEG_LEN`-frame window to exist at all: the
match this task's `no_window` gate is built for.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import duckdb
import pytest

from tracklab.quality import entry_angle as ea
from tracklab.quality.common import report_path
from tracklab.quality.flight import G
from tracklab.quality.gravity import RIM_X
from tracklab.quality.run import run_quality

FPS = 25
DT = 1.0 / FPS

# The engineered flight: horizontal speed, release height and constant fall rate
# near the arrival frame, all exact numbers so the expected angles are computed
# by hand below, once, the same way the check does.
V_H = 5.0  # m/s
Z0 = 2.0  # m, height at the search-start frame (frame 2, startFrame + 2)
V_FALL = 3.0  # m/s, the (unphysical, deliberately linear) fall rate near arrival
T_FLIGHT = 1.0  # s; D = V_H * T_FLIGHT
X0 = RIM_X - V_H * T_FLIGHT  # so the horizontal distance to the rim is exactly D

Row = tuple[str, str, int, int, int, int, str, float, float, float]


def _ball_series(native: int, n_frames: int) -> list[Row]:
    """`n_frames` ball samples of the engineered flight, frames 0..n_frames-1.
    `t=0` sits at frame 2 (`startFrame=0`, `SEARCH_OFFSET=2`)."""
    rows: list[Row] = []
    for f in range(n_frames):
        t = (f - 2) * DT
        x, y, z = X0 + V_H * t, 0.0, Z0 - V_FALL * t
        rows.append(("basketball", f"bb:{native}", native, 1, f, f * 40, "ball", x, y, z))
    return rows


def _values(rows: list[tuple[object, ...]]) -> str:
    return ", ".join(repr(tuple(row)) for row in rows)


def _write(data_dir: Path, ball_rows: list[Row], shots: list[tuple[object, ...]]) -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE frames (sport VARCHAR, match_id VARCHAR, native_match_id BIGINT,
            period SMALLINT, frame_native BIGINT, t_ms BIGINT, entity_kind VARCHAR,
            x_m DOUBLE, y_m DOUBLE, z_m DOUBLE)
        """
    )
    con.execute(f"INSERT INTO frames VALUES {_values(ball_rows)}")
    frames = data_dir / "silver" / "frames"
    frames.mkdir(parents=True)
    con.execute(
        f"COPY frames TO '{frames.as_posix()}' "
        "(FORMAT PARQUET, PARTITION_BY (sport, native_match_id))"
    )
    con.execute(
        """
        CREATE TABLE shots (match_id BIGINT, id VARCHAR, startFrame BIGINT, endFrame BIGINT,
            blocked BOOLEAN, outcome BOOLEAN, distance DOUBLE)
        """
    )
    con.execute(f"INSERT INTO shots VALUES {_values(shots)}")
    bronze = data_dir / "bronze" / "basketball" / "events_shots"
    bronze.mkdir(parents=True)
    for native in {int(s[0]) for s in shots}:
        path = (bronze / f"{native}.parquet").as_posix()
        con.execute(f"COPY (SELECT * FROM shots WHERE match_id = {native}) TO '{path}'")


def _expected_angles() -> tuple[float, float]:
    """(reported, required) in degrees, by hand, from the module's own formula."""
    ang_rep = math.degrees(math.atan2(V_FALL, V_H))
    v_z0 = (ea.RIM_HEIGHT - Z0 + 0.5 * G * T_FLIGHT * T_FLIGHT) / T_FLIGHT
    ang_req = math.degrees(math.atan2(abs(v_z0 - G * T_FLIGHT), V_H))
    return ang_rep, ang_req


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, str], tuple[float, int]]:
    root = tmp_path_factory.mktemp("entry_angle")
    good = _ball_series(999999, 46)  # a full SEG_LEN(=40)-frame window, and margin
    short = _ball_series(999998, 20)  # not enough frames after startFrame + 2
    shots = [
        (999999, "shot-good", 0, 30, False, True, 20.0),
        (999998, "shot-short", 0, 30, False, True, 20.0),
    ]
    _write(root / "data", good + short, shots)
    reports = root / "reports"
    assert run_quality(["entry_angle"], data_dir=root / "data", reports_dir=reports) == 0
    with report_path(reports, "entry_angle").open(encoding="utf-8", newline="") as handle:
        return {
            (r["match_id"], r["metric"]): (float(r["value"]), int(r["n"]))
            for r in csv.DictReader(handle)
        }


def test_the_engineered_flight_gives_the_hand_computed_angles(
    report: dict[tuple[str, str], tuple[float, int]],
) -> None:
    ang_rep, ang_req = _expected_angles()
    assert report[("bb:999999", "angle_reported_median_deg")] == (
        pytest.approx(ang_rep, abs=5e-5),
        1,
    )
    assert report[("bb:999999", "angle_required_median_deg")] == (
        pytest.approx(ang_req, abs=5e-5),
        1,
    )
    gap = ang_req - ang_rep
    assert report[("bb:999999", "gap_median_deg")] == (pytest.approx(gap, abs=5e-5), 1)
    assert report[("bb:999999", "shots")] == (1.0, 1)
    assert report[("bb:999999", "candidates")] == (1.0, 1)
    # A single shot has no pair to reorder against.
    assert ("bb:999999", "pairs_reordered_pct") not in report


def test_too_few_ball_frames_after_the_shot_is_excluded(
    report: dict[tuple[str, str], tuple[float, int]],
) -> None:
    assert report[("bb:999998", "shots")] == (0.0, 1)
    assert report[("bb:999998", "excluded_no_window")] == (1.0, 1)
    for reason in ("short_run", "slow_ball", "bad_flight_time", "arrival_beyond_run"):
        assert report[("bb:999998", f"excluded_{reason}")] == (0.0, 1)


def test_shrinking_the_window_moves_the_short_match_past_no_window(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation: with `SEG_LEN` small enough for 20 ball frames to hold a window,
    the shot no longer trips `no_window` -- it now reaches `arrival_beyond_run`
    instead, because a T=1.0 s flight (25 frames at 25 fps) can never fit inside
    a 15-frame run. Proof the gate removed is the one that was biting, not a
    dead branch: the exclusion moves, it does not vanish."""
    root = tmp_path_factory.mktemp("entry_angle_mutated")
    short = _ball_series(999998, 20)
    shots = [(999998, "shot-short", 0, 30, False, True, 20.0)]
    _write(root / "data", short, shots)
    monkeypatch.setattr(ea, "SEG_LEN", 15)

    results = ea.entry_angle(root / "data", root / "reports")
    by_metric = {r.metric: r.value for r in results if r.match_id == "bb:999998"}
    assert by_metric["excluded_no_window"] == 0.0
    assert by_metric["excluded_arrival_beyond_run"] == 1.0
    assert by_metric["shots"] == 0.0
