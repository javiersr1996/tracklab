"""`tracklab quality gravity` on a fabricated `frames` and bronze `events_shots`.

Every flight is an exact parabola with a g chosen here, not 9.80665, so a check that
returned the constant would fail. The ball rests on the floor between flights.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import duckdb
import pytest

from tracklab.quality.common import report_path
from tracklab.quality.gravity import FB_FLIGHT_Z, RIM_X
from tracklab.quality.run import run_quality

G_BB, G_FB = 8.0, 8.5
BB_FPS, FB_FPS = 25, 10
SHOT_FRAMES = 200  # each shot owns this many frames, its flight in the middle

Row = tuple[str, str, int, int, int, int, str, float, float, float]


def _flight(apex_z: float, g: float, dt: float, floor: float) -> float:
    return max(apex_z - 0.5 * g * dt * dt, floor)


def _basketball(native: int, shots: list[tuple[str, bool]]) -> tuple[list[Row], list[tuple]]:
    """One flight per shot, apex 4.5 m at the shot's frame 100. `clean` travels well
    short of the rim; `rim` crosses a rim axis 5 frames after the apex."""
    rows: list[Row] = []
    events: list[tuple] = []
    for k, (kind, blocked) in enumerate(shots):
        base = k * SHOT_FRAMES
        apex = base + 100
        for f in range(base, base + SHOT_FRAMES):
            dt = (f - apex) / BB_FPS
            x = RIM_X - 5 * 0.3 + (f - apex) * 0.3 if kind == "rim" else -3.0 + dt
            z = _flight(4.5, G_BB, dt, 0.12)
            row = ("basketball", f"bb:{native}", native, 1, f, f * 40, "ball", x, 0.0, z)
            rows.append(row)
        rows.append(("basketball", f"bb:{native}", native, 1, apex, apex * 40, "player", 0, 0, 0))
        events.append((native, f"shot-{native}-{k}", apex - 15, apex + 10, blocked))
    return rows, events


def _football(native: int, apexes: list[float]) -> list[Row]:
    """Flights 60 frames apart, each from a ball resting at 0.11 m."""
    rows: list[Row] = []
    for k, apex_z in enumerate(apexes):
        apex = k * 60 + 30
        for f in range(k * 60, k * 60 + 60):
            z = _flight(apex_z, G_FB, (f - apex) / FB_FPS, 0.11)
            rows.append(("football", f"fb:{native}", native, 1, f, f * 100, "ball", 0, 0, z))
    return rows


def _values(rows: list[Row] | list[tuple]) -> str:
    """A VALUES list: one statement is far faster than one insert per row."""
    return ", ".join(repr(tuple(row)) for row in rows)


def _write(data_dir: Path, rows: list[Row], shots: list[tuple]) -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE frames (sport VARCHAR, match_id VARCHAR, native_match_id BIGINT,
            period SMALLINT, frame_native BIGINT, t_ms BIGINT, entity_kind VARCHAR,
            x_m DOUBLE, y_m DOUBLE, z_m DOUBLE)
        """
    )
    con.execute(f"INSERT INTO frames VALUES {_values(rows)}")
    frames = data_dir / "silver" / "frames"
    frames.mkdir(parents=True)
    con.execute(
        f"COPY frames TO '{frames.as_posix()}' "
        "(FORMAT PARQUET, PARTITION_BY (sport, native_match_id))"
    )
    con.execute(
        """
        CREATE TABLE shots (match_id BIGINT, id VARCHAR, startFrame BIGINT, endFrame BIGINT,
            blocked BOOLEAN)
        """
    )
    con.execute(f"INSERT INTO shots VALUES {_values(shots)}")
    bronze = data_dir / "bronze" / "basketball" / "events_shots"
    bronze.mkdir(parents=True)
    for native in {s[0] for s in shots}:
        path = (bronze / f"{native}.parquet").as_posix()
        con.execute(f"COPY (SELECT * FROM shots WHERE match_id = {native}) TO '{path}'")


def _report(root: Path) -> dict[tuple[str, str, str], tuple[float, int]]:
    reports = root / "reports"
    assert run_quality(["gravity"], data_dir=root / "data", reports_dir=reports) == 0
    with report_path(reports, "gravity").open(encoding="utf-8", newline="") as handle:
        return {
            (r["sport"], r["match_id"], r["metric"]): (float(r["value"]), int(r["n"]))
            for r in csv.DictReader(handle)
        }


@pytest.fixture(scope="module")
def report(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[tuple[str, str, str], tuple[float, int]]:
    root = tmp_path_factory.mktemp("gravity")
    calib, calib_shots = _basketball(
        114243, [("clean", False), ("clean", False), ("rim", False), ("clean", True)]
    )
    control, control_shots = _basketball(178442, [("clean", False), ("clean", False)])
    football = _football(1874553, [6.0, 1.8, 5.0])
    _write(root / "data", calib + control + football, calib_shots + control_shots)
    return _report(root)


def test_basketball_gives_back_the_fabricated_g(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    for match in ("bb:114243", "bb:178442"):
        for metric in ("g_median", "g_q1", "g_q3"):
            assert report[("basketball", match, metric)] == (pytest.approx(G_BB, rel=1e-4), 2)
    bias = 100 * (G_BB / 9.80665 - 1)
    assert report[("basketball", "bb:114243", "g_median_bias_pct")][0] == pytest.approx(
        bias, abs=1e-3
    )


def test_a_flight_that_reaches_the_rim_after_its_apex_is_excluded(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    metrics = ("shots", "excluded_blocked", "excluded_no_window", "excluded_rebound")
    metrics += ("excluded_residual", "flights")
    got = {m: report[("basketball", "bb:114243", m)][0] for m in metrics}
    assert got == {
        "shots": 4,
        "excluded_blocked": 1,
        "excluded_no_window": 0,
        "excluded_rebound": 1,
        "excluded_residual": 0,
        "flights": 2,
    }


def test_matches_are_flagged_calibration_or_control(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    assert report[("basketball", "bb:114243", "is_calibration")][0] == 1.0
    assert report[("basketball", "bb:178442", "is_calibration")][0] == 0.0


def test_football_flights_and_a_window_that_leaves_the_air(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    # The 1.8 m flight is above 1 m for less than +-6 frames of its apex.
    assert math.sqrt(2 * (1.8 - FB_FLIGHT_Z) / G_FB) * FB_FPS < 6
    metrics = ("flights_detected", "excluded_window_leaves_flight", "flights")
    got = {m: report[("football", "fb:1874553", m)][0] for m in metrics}
    assert got == {"flights_detected": 3, "excluded_window_leaves_flight": 1, "flights": 2}
    assert report[("football", "fb:1874553", "g_median")] == (
        pytest.approx(G_FB, rel=1e-4),
        2,
    )
    assert ("football", "fb:1874553", "is_calibration") not in report
