"""`tracklab quality gravity` on a fabricated `frames`, bronze `events_shots` and
silver `events`.

Every flight is an exact parabola with a g chosen here, not 9.80665, so a check that
returned the constant would fail. The ball rests on the floor between flights.
Every basketball sample is flagged undetected, as in the bundle; football's flags and
player possessions are set per flight.
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
FB_NATIVE = 1874553

Row = tuple[str, str, int, int, int, int, str, float, float, float, bool]


def _flight(apex_z: float, g: float, dt: float, floor: float) -> float:
    return max(apex_z - 0.5 * g * dt * dt, floor)


def _basketball(native: int, shots: list[tuple[str, bool]]) -> tuple[list[Row], list[tuple]]:
    """One flight per shot, apex at the shot's frame 100. `clean` peaks at 4.5 m and
    travels well short of the rim; `rim` crosses a rim axis 5 frames after the apex;
    `low` peaks at 3.2 m and drops below `FLOOR` inside the window; `noisy` is the
    clean flight with +-0.4 m of alternating vertical noise, a residual RMS above
    `MAX_RMS`."""
    rows: list[Row] = []
    events: list[tuple] = []
    for k, (kind, blocked) in enumerate(shots):
        base = k * SHOT_FRAMES
        apex = base + 100
        for f in range(base, base + SHOT_FRAMES):
            dt = (f - apex) / BB_FPS
            x = RIM_X - 5 * 0.3 + (f - apex) * 0.3 if kind == "rim" else -3.0 + dt
            z = _flight(3.2 if kind == "low" else 4.5, G_BB, dt, 0.12)
            if kind == "noisy":
                z += 0.4 if f % 2 == 0 else -0.4
            row = ("basketball", f"bb:{native}", native, 1, f, f * 40, "ball", x, 0.0, z, False)
            rows.append(row)
        player = ("basketball", f"bb:{native}", native, 1, apex, apex * 40, "player", 0, 0, 0)
        rows.append((*player, False))
        events.append((native, f"shot-{native}-{k}", apex - 15, apex + 10, blocked))
    return rows, events


def _football(native: int, flights: list[tuple[float, int | None]]) -> list[Row]:
    """Flights 60 frames apart, apex at frame 60k + 30, each from a ball resting at
    0.11 m. The second item of a flight, when set, is the offset from the apex of its
    one undetected sample."""
    rows: list[Row] = []
    for k, (apex_z, undetected) in enumerate(flights):
        apex = k * 60 + 30
        for f in range(k * 60, k * 60 + 60):
            z = _flight(apex_z, G_FB, (f - apex) / FB_FPS, 0.11)
            detected = undetected is None or f != apex + undetected
            row = ("football", f"fb:{native}", native, 1, f, f * 100, "ball", 0, 0, z, detected)
            rows.append(row)
    return rows


def _values(rows: list[Row] | list[tuple]) -> str:
    """A VALUES list: one statement is far faster than one insert per row."""
    return ", ".join(repr(tuple(row)) for row in rows)


def _write(data_dir: Path, rows: list[Row], shots: list[tuple], possessions: list[tuple]) -> None:
    """`possessions`: (sport, native match id, frame_start, frame_end) of player
    possessions, written to silver `events`."""
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE frames (sport VARCHAR, match_id VARCHAR, native_match_id BIGINT,
            period SMALLINT, frame_native BIGINT, t_ms BIGINT, entity_kind VARCHAR,
            x_m DOUBLE, y_m DOUBLE, z_m DOUBLE, is_detected BOOLEAN)
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
    con.execute(
        """
        CREATE TABLE events (sport VARCHAR, native_match_id BIGINT, native_family VARCHAR,
            frame_start BIGINT, frame_end BIGINT)
        """
    )
    rows_events = [(s, m, "player_possession", a, b) for s, m, a, b in possessions]
    # A football event of another family at an apex frame: not a touch.
    rows_events.append(("football", FB_NATIVE, "on_ball_engagement", 30, 30))
    con.execute(f"INSERT INTO events VALUES {_values(rows_events)}")
    events = data_dir / "silver" / "events"
    events.mkdir(parents=True)
    con.execute(
        f"COPY events TO '{events.as_posix()}' "
        "(FORMAT PARQUET, PARTITION_BY (sport, native_match_id))"
    )


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
        114243,
        [
            ("clean", False),
            ("clean", False),
            ("rim", False),
            ("clean", True),
            ("low", False),
            ("noisy", False),
        ],
    )
    control, control_shots = _basketball(178442, [("clean", False), ("clean", False)])
    # Apexes at 30, 90, 150, 210, 270 and 330. Kept: 6.0 m (a possession ends 7 frames
    # before the apex, one frame outside the +-6 window) and 5.0 m (undetected 7 frames
    # after it). Dropped: 1.8 m (the window leaves the air), 5.5 m (undetected at apex
    # + 6), 5.2 m (a possession starts at apex + 6) and 5.4 m (one ends at apex - 6).
    flights = [(6.0, None), (1.8, None), (5.0, 7), (5.5, 6), (5.2, None), (5.4, None)]
    possessions = [
        ("football", FB_NATIVE, 30 - 10, 30 - 7),
        ("football", FB_NATIVE, 270 + 6, 270 + 9),
        ("football", FB_NATIVE, 330 - 9, 330 - 6),
        # Basketball's possessions are not football touches, even at the same frames.
        ("basketball", FB_NATIVE, 150, 150),
    ]
    rows = calib + control + _football(FB_NATIVE, flights)
    _write(root / "data", rows, calib_shots + control_shots, possessions)
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


def test_rebound_and_residual_cuts_on_basketball(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    metrics = ("shots", "excluded_blocked", "excluded_no_window", "excluded_rebound")
    metrics += ("excluded_residual", "flights")
    got = {m: report[("basketball", "bb:114243", m)][0] for m in metrics}
    # The rim flight and the low one rebound; the noisy one fails the residual cut.
    # Basketball ignores `is_detected` (always false for its ball).
    assert got == {
        "shots": 6,
        "excluded_blocked": 1,
        "excluded_no_window": 0,
        "excluded_rebound": 2,
        "excluded_residual": 1,
        "flights": 2,
    }


def test_matches_are_flagged_calibration_or_control(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    assert report[("basketball", "bb:114243", "is_calibration")][0] == 1.0
    assert report[("basketball", "bb:178442", "is_calibration")][0] == 0.0


def test_football_window_detection_and_possession_cuts(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    # The 1.8 m flight is above 1 m for less than +-6 frames of its apex; the lowest
    # of the others stays above it for more than +-7.
    assert math.sqrt(2 * (1.8 - FB_FLIGHT_Z) / G_FB) * FB_FPS < 6
    assert math.sqrt(2 * (5.0 - FB_FLIGHT_Z) / G_FB) * FB_FPS > 7
    metrics = (
        "flights_detected",
        "excluded_window_leaves_flight",
        "excluded_undetected",
        "excluded_player_possession",
        "excluded_residual",
        "flights",
    )
    got = {m: report[("football", f"fb:{FB_NATIVE}", m)][0] for m in metrics}
    assert got == {
        "flights_detected": 6,
        "excluded_window_leaves_flight": 1,
        "excluded_undetected": 1,
        "excluded_player_possession": 2,
        "excluded_residual": 0,
        "flights": 2,
    }
    assert report[("football", f"fb:{FB_NATIVE}", "g_median")] == (
        pytest.approx(G_FB, rel=1e-4),
        2,
    )
    assert ("football", f"fb:{FB_NATIVE}", "is_calibration") not in report
