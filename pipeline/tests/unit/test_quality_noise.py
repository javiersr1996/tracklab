"""`tracklab quality noise` on a fabricated, partitioned `frames` and bronze
`tracking_objects` (basketball's `predError`).

Every second difference is exact by construction: a horizontal position
oscillates by a fixed amplitude every other frame and nothing else, so
`x(f+1) - 2x(f) + x(f-1) = -4 * amplitude * (-1)^f` at every interior frame
(the alternation has no other Fourier content for a second difference to
catch), and the per-frame step is the constant `2 * amplitude / dt`, comfortably
above `MOVING_MPS` for every amplitude used here. The ball's amplitude is a
multiple of the player's so the reported ratio is exact too.
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest

from tracklab.quality import noise
from tracklab.quality.common import report_path
from tracklab.quality.run import run_quality

BB_FPS, FB_FPS = 25, 10
N = 20  # frames per run; well above MIN_RUN (12)

Row = tuple[str, str, int, int, int, str, str, float, float]


def _jitter_run(
    sport: str, native: int, entity_kind: str, entity_id: str, amplitude: float, fps: int
) -> list[Row]:
    """`N` frames oscillating by `+-amplitude`: `d2 == 4 * amplitude` and the
    step is the constant `2 * amplitude * fps`, both exact (see module docstring)."""
    match_id = f"{'bb' if sport == 'basketball' else 'fb'}:{native}"
    rows: list[Row] = []
    for f in range(N):
        x = amplitude if f % 2 == 0 else -amplitude
        rows.append((sport, match_id, native, f, f * 1000 // fps, entity_kind, entity_id, x, 0.0))
    return rows


def _still_run(sport: str, native: int, entity_kind: str, entity_id: str, fps: int) -> list[Row]:
    """Never moves: every step is 0, so it never passes the `MOVING_MPS` gate and
    contributes no second difference at all."""
    match_id = f"{'bb' if sport == 'basketball' else 'fb'}:{native}"
    return [
        (sport, match_id, native, f, f * 1000 // fps, entity_kind, entity_id, 0.0, 0.0)
        for f in range(N)
    ]


def _values(rows: list[tuple[object, ...]]) -> str:
    return ", ".join(repr(tuple(row)) for row in rows)


def _write(data_dir: Path, rows: list[Row], pred_errors: list[tuple[object, ...]]) -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE frames (sport VARCHAR, match_id VARCHAR, native_match_id BIGINT,
            frame_native BIGINT, t_ms BIGINT, entity_kind VARCHAR, entity_id VARCHAR,
            x_m DOUBLE, y_m DOUBLE, is_detected BOOLEAN)
        """
    )
    with_detected = [(*r, True) for r in rows]
    con.execute(f"INSERT INTO frames VALUES {_values(with_detected)}")
    frames = data_dir / "silver" / "frames"
    frames.mkdir(parents=True)
    con.execute(
        f"COPY frames TO '{frames.as_posix()}' "
        "(FORMAT PARQUET, PARTITION_BY (sport, native_match_id))"
    )
    con.execute(
        "CREATE TABLE objects (match_id BIGINT, side VARCHAR, isDetected BOOLEAN, predError DOUBLE)"
    )
    con.execute(f"INSERT INTO objects VALUES {_values(pred_errors)}")
    bronze = data_dir / "bronze" / "basketball" / "tracking_objects"
    bronze.mkdir(parents=True)
    for native in {int(p[0]) for p in pred_errors}:
        path = (bronze / f"{native}.parquet").as_posix()
        con.execute(f"COPY (SELECT * FROM objects WHERE match_id = {native}) TO '{path}'")


@pytest.fixture(scope="module")
def report(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[tuple[str, str, str], tuple[float, int]]:
    root = tmp_path_factory.mktemp("noise")
    # Basketball 1: ball jitters 4x the player's amplitude; both clear the moving gate.
    bb_ball = _jitter_run("basketball", 1, "ball", "ball", amplitude=0.20, fps=BB_FPS)
    bb_player = _jitter_run("basketball", 1, "player", "p1", amplitude=0.05, fps=BB_FPS)
    bb_still = _still_run("basketball", 1, "player", "p2", fps=BB_FPS)
    # Football: same construction, a different sport and fps to prove it is not hard-coded.
    fb_ball = _jitter_run("football", 2, "ball", "ball", amplitude=0.10, fps=FB_FPS)
    fb_player = _jitter_run("football", 2, "player", "p1", amplitude=0.05, fps=FB_FPS)
    pred_errors = [
        (1, "ball", True, 1.5),
        (1, "ball", True, 1.5),
        (1, "home", True, 0.9),
        (1, "home", False, 99.0),  # not detected: excluded from the player median
    ]
    _write(root / "data", bb_ball + bb_player + bb_still + fb_ball + fb_player, pred_errors)
    reports = root / "reports"
    assert run_quality(["noise"], data_dir=root / "data", reports_dir=reports) == 0
    with report_path(reports, "noise").open(encoding="utf-8", newline="") as handle:
        return {
            (r["sport"], r["match_id"], r["metric"]): (float(r["value"]), int(r["n"]))
            for r in csv.DictReader(handle)
        }


def test_basketball_second_differences_and_ratio_are_exact(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    ball_d2, ball_n = report[("basketball", "bb:1", "ball_d2_median_m")]
    player_d2, player_n = report[("basketball", "bb:1", "player_d2_median_m")]
    assert ball_d2 == pytest.approx(0.8, abs=1e-9)  # 4 * 0.20
    assert player_d2 == pytest.approx(0.2, abs=1e-9)  # 4 * 0.05
    assert ball_n > 0 and player_n > 0
    ratio, _ = report[("basketball", "bb:1", "ball_player_d2_ratio")]
    assert ratio == pytest.approx(4.0, abs=1e-6)


def test_a_still_player_contributes_no_second_difference(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    # The still player (p2) never clears MOVING_MPS, so the pooled player d2 is
    # exactly the moving player's (p1) own runs, unaffected by the still one.
    assert report[("basketball", "bb:1", "player_d2_median_m")][0] == pytest.approx(0.2, abs=1e-9)


def test_basketball_declares_prederror_football_does_not(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    assert report[("basketball", "bb:1", "ball_pred_error_median_m")][0] == pytest.approx(
        1.5 * noise.FT, abs=1e-9
    )
    assert report[("basketball", "bb:1", "player_pred_error_median_m")] == (
        pytest.approx(0.9 * noise.FT, abs=1e-9),
        1,
    )
    assert ("football", "fb:2", "ball_pred_error_median_m") not in report
    assert ("football", "fb:2", "player_pred_error_median_m") not in report


def test_football_ratio_uses_the_same_construction_at_a_different_fps(
    report: dict[tuple[str, str, str], tuple[float, int]],
) -> None:
    assert report[("football", "fb:2", "ball_d2_median_m")][0] == pytest.approx(0.4, abs=1e-9)
    assert report[("football", "fb:2", "player_d2_median_m")][0] == pytest.approx(0.2, abs=1e-9)
    assert report[("football", "fb:2", "ball_player_d2_ratio")][0] == pytest.approx(2.0, abs=1e-6)


def test_raising_the_moving_gate_above_the_players_step_empties_it(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation: the player's own step is a constant `2 * 0.05 * 25 = 2.5` m/s.
    Raising `MOVING_MPS` past that drops every one of the player's samples --
    proof the gate is what selects them, not a no-op -- while the ball's step
    (`2 * 0.20 * 25 = 10` m/s) still clears it."""
    root = tmp_path_factory.mktemp("noise_mutated")
    bb_ball = _jitter_run("basketball", 1, "ball", "ball", amplitude=0.20, fps=BB_FPS)
    bb_player = _jitter_run("basketball", 1, "player", "p1", amplitude=0.05, fps=BB_FPS)
    _write(root / "data", bb_ball + bb_player, [(1, "ball", True, 1.5)])
    monkeypatch.setattr(noise, "MOVING_MPS", 3.0)

    results = noise.noise(root / "data", root / "reports")
    metrics = {r.metric for r in results if r.match_id == "bb:1"}
    assert "player_d2_median_m" not in metrics
    assert "ball_d2_median_m" in metrics
