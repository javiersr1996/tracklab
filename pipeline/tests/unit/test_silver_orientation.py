"""silver.orientation on a synthetic bronze in ``tmp_path``: no real data, no network.

One basketball match (two periods, home 10 and away 20) and one football match (two
periods, home 7 and away 8) are written as bronze-shaped Parquet with only the columns
the probe reads. Every planted number below is chosen so the expected count is known
by hand: the shot probe matches 4 shots exactly and loses one to each exclusion (no
location, no possession, no shooter at that frame); the football events are planted in
the attack frame so the *attack* hypothesis matches every row and *venue* only the
left-to-right one. The end-to-end tests go through the CLI exactly as a user would and
read the artefacts back.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tracklab.bronze.common import bronze_path
from tracklab.cli import main
from tracklab.ingest.manifest import FileEntry, Manifest, Source, save_manifest
from tracklab.silver.orientation import (
    DOC_ABOVE,
    DOC_BELOW,
    FIBA,
    NBA,
    ORIENTATION_SCHEMA,
    SHOT_TOL_FT,
    attack_sign_from_left_hoop,
    attack_sign_from_side,
    basketball_shot_probe,
    basketball_signs,
    fit_three_radius,
    football_event_probe,
    football_signs,
    load_report,
    orientation_path,
    report_path,
    to_attack_factor,
)

BB_MATCH, BB_HOME, BB_AWAY = 700001, 10, 20
FB_MATCH, FB_HOME, FB_AWAY = 800001, 7, 8
COMMIT = "0" * 40

Columns = dict[str, tuple[pa.DataType, list[Any]]]


def _write(data_dir: Path, sport: str, table: str, match_id: int, columns: Columns) -> None:
    path = bronze_path(data_dir, sport, table, match_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    table_ = pa.table({name: pa.array(values, type=t) for name, (t, values) in columns.items()})
    pq.write_table(table_, path)


def _dist(x: float, y: float) -> float:
    return math.hypot(x - FIBA.hoop_x_ft, y)


def bb_shots(shift_y: float = 0.0, flip_a: bool = False) -> Columns:
    """Seven shots: A, B, C, G match the planted tracking; D has no shooter position at
    its frame, E no location, F a possession id that does not exist. ``shift_y`` moves
    shot A's declared location away from the shooter (a residual the share must show);
    ``flip_a`` puts A's location where the OPPOSITE rotation predicts (what the binary
    check must refuse)."""
    xs = [30.0 if flip_a else -30.0, -30.0, -25.0, -20.0, None, -10.0, -18.0]
    ys = [-5.0 if flip_a else 5.0 + shift_y, 5.0, 0.0, -3.0, None, 0.0, 0.0]
    dist = [None if x is None else _dist(x, y) for x, y in zip(xs, ys, strict=True)]
    return {
        "id": (pa.string(), ["s-A", "s-B", "s-C", "s-D", "s-E", "s-F", "s-G"]),
        "period": (pa.int64(), [1, 1, 2, 2, 1, 1, 1]),
        "offTeamId": (pa.int64(), [BB_HOME, BB_AWAY, BB_HOME, BB_AWAY, BB_HOME, BB_HOME, BB_HOME]),
        "possessionId": (
            pa.string(),
            ["pos-1", "pos-3", "pos-4", "pos-5", "pos-1", "nope", "pos-2"],
        ),
        "startFrame": (pa.int64(), [100, 200, 300, 400, 500, 600, 700]),
        "shooterId": (pa.int64(), [101, 201, 101, 201, 101, 101, 101]),
        "location_x": (pa.float64(), xs),
        "location_y": (pa.float64(), ys),
        "distance": (pa.float64(), dist),
        "three": (
            pa.bool_(),
            [d is not None and d >= FIBA.three_radius_ft for d in dist],
        ),
        "touchId": (pa.string(), ["t-A", None, "t-C", None, None, None, None]),
    }


def bb_tracking(a_detected: bool = True, a_later: tuple[float, float] | None = None) -> Columns:
    """The shooters' positions at the shot frames. ``a_later`` adds a position of shooter
    101 ten frames after shot A, so a shifted location can be found there."""
    frames = [100, 200, 300, 500, 600, 700]
    players = [101, 201, 101, 101, 101, 101]
    xs = [-30.0, 30.0, 25.0, -12.0, -10.0, -18.0]
    ys = [5.0, -5.0, 0.0, 1.0, 0.0, 0.0]
    detected = [a_detected, True, True, True, True, True]
    errors = [9.0 if not a_detected else 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
    if a_later is not None:
        frames.append(110)
        players.append(101)
        xs.append(a_later[0])
        ys.append(a_later[1])
        detected.append(True)
        errors.append(0.5)
    return {
        "frameIdx": (pa.int64(), frames),
        "playerId": (pa.int64(), players),
        "x": (pa.float64(), xs),
        "y": (pa.float64(), ys),
        "isDetected": (pa.bool_(), detected),
        "predError": (pa.float64(), errors),
    }


def write_basketball(
    data_dir: Path,
    possessions: Columns | None = None,
    shots: Columns | None = None,
    tracking: Columns | None = None,
) -> None:
    _write(
        data_dir,
        "basketball",
        "games",
        BB_MATCH,
        {"homeTeamId": (pa.int64(), [BB_HOME]), "awayTeamId": (pa.int64(), [BB_AWAY])},
    )
    _write(
        data_dir,
        "basketball",
        "events_possessions",
        BB_MATCH,
        possessions
        or {
            "id": (pa.string(), ["pos-1", "pos-2", "pos-3", "pos-4", "pos-5"]),
            "period": (pa.int64(), [1, 1, 1, 2, 2]),
            "offTeamId": (pa.int64(), [BB_HOME, BB_HOME, BB_AWAY, BB_HOME, BB_AWAY]),
            "leftHoop": (pa.bool_(), [True, True, False, False, True]),
        },
    )
    _write(data_dir, "basketball", "events_shots", BB_MATCH, shots or bb_shots())
    _write(data_dir, "basketball", "tracking_objects", BB_MATCH, tracking or bb_tracking())
    _write(
        data_dir,
        "basketball",
        "events_touches",
        BB_MATCH,
        {
            "id": (pa.string(), ["t-A", "t-C"]),
            "endLoc_x": (pa.float64(), [-30.0, -25.0]),
            "endLoc_y": (pa.float64(), [5.0, 0.0]),
        },
    )
    _write(
        data_dir,
        "basketball",
        "events_rebounds",
        BB_MATCH,
        {"location_x": (pa.float64(), [-38.0, None]), "location_y": (pa.float64(), [2.0, None])},
    )


def write_football(data_dir: Path, phases: Columns | None = None) -> None:
    _write(
        data_dir,
        "football",
        "match",
        FB_MATCH,
        {
            "home_team_id": (pa.int64(), [FB_HOME]),
            "away_team_id": (pa.int64(), [FB_AWAY]),
            "home_team_side": (pa.list_(pa.string()), [["right_to_left", "left_to_right"]]),
        },
    )
    _write(data_dir, "football", "match_periods", FB_MATCH, {"period": (pa.int64(), [1, 2])})
    _write(
        data_dir,
        "football",
        "phases_of_play",
        FB_MATCH,
        phases
        or {
            "period": (pa.int64(), [1, 1, 1, 2, 2, 2]),
            "team_in_possession_id": (
                pa.int64(),
                [FB_HOME, FB_HOME, FB_AWAY, FB_HOME, FB_AWAY, FB_AWAY],
            ),
            "attacking_side": (
                pa.string(),
                [
                    "right_to_left",
                    "right_to_left",
                    "left_to_right",
                    "left_to_right",
                    "right_to_left",
                    "right_to_left",
                ],
            ),
        },
    )
    pp = "player_possession"
    _write(
        data_dir,
        "football",
        "dynamic_events",
        FB_MATCH,
        {
            "event_type": (pa.string(), [pp, pp, pp, pp, pp, "off_ball_run"]),
            "player_id": (pa.int64(), [71, 81, 71, 99, 71, 71]),
            "frame_start": (pa.int64(), [10, 20, 30, 40, 50, 60]),
            "x_start": (pa.float64(), [20.0, 10.0, 5.0, 1.0, None, 3.0]),
            "y_start": (pa.float64(), [8.0, 3.0, -1.0, 1.0, None, 3.0]),
            "attacking_side": (
                pa.string(),
                [
                    "right_to_left",
                    "left_to_right",
                    "right_to_left",
                    "right_to_left",
                    "left_to_right",
                    "left_to_right",
                ],
            ),
        },
    )
    _write(
        data_dir,
        "football",
        "tracking_objects",
        FB_MATCH,
        {
            "frame": (pa.int64(), [10, 20, 30, 50, 60]),
            "player_id": (pa.int64(), [71, 81, 71, 71, 71]),
            "x": (pa.float64(), [-20.0, 10.0, -5.0, 0.0, 3.0]),
            "y": (pa.float64(), [-8.0, 3.0, 1.0, 0.0, 3.0]),
        },
    )
    _write(
        data_dir,
        "football",
        "match_players",
        FB_MATCH,
        {"last_modified": (pa.string(), [None, None])},
    )


def _source(source_id: str, sport: str, match_id: int) -> Source:
    return Source(
        source_id=source_id,
        sport=sport,
        kind="github",
        repo="SkillCorner/x",
        ref="main",
        commit=COMMIT,
        license="MIT",
        raw_url="https://raw.githubusercontent.com/SkillCorner/x/{commit}/",
        lfs_url="https://media.githubusercontent.com/media/SkillCorner/x/{commit}/",
        files=[
            FileEntry(
                path=f"data/matches/{match_id}/tracking",
                bytes=0,
                sha256="0" * 64,
                lfs=True,
                role="tracking",
                match_id=match_id,
            )
        ],
    )


@pytest.fixture
def bundle(tmp_path: Path) -> dict[str, Path]:
    data_dir = tmp_path / "data"
    write_basketball(data_dir)
    write_football(data_dir)
    manifest_path = tmp_path / "sources.json"
    save_manifest(
        Manifest(
            schema_version=1,
            sources=[
                _source("opendata-basketball", "basketball", BB_MATCH),
                _source("opendata-football", "football", FB_MATCH),
            ],
        ),
        manifest_path,
    )
    return {
        "manifest": manifest_path,
        "data": data_dir,
        "reports": tmp_path / "reports",
        "docs": tmp_path / "docs",
    }


def run_cli(paths: dict[str, Path], sport: str = "both") -> int:
    return main(
        [
            "orientation",
            "--sport",
            sport,
            "--manifest",
            str(paths["manifest"]),
            "--data-dir",
            str(paths["data"]),
            "--reports-dir",
            str(paths["reports"]),
            "--docs-dir",
            str(paths["docs"]),
        ]
    )


# --- the two rules ---------------------------------------------------------------------


def test_attack_sign_rules() -> None:
    assert attack_sign_from_left_hoop(True) == -1, "leftHoop: the offence attacks negative x"
    assert attack_sign_from_left_hoop(False) == 1
    assert to_attack_factor(True) == 1, "venue coordinates already are the attack frame"
    assert to_attack_factor(False) == -1
    assert attack_sign_from_side("left_to_right") == 1
    assert attack_sign_from_side("right_to_left") == -1
    with pytest.raises(ValueError, match="unknown attacking side 'up'"):
        attack_sign_from_side("up")


# --- basketball ------------------------------------------------------------------------


def test_basketball_signs_from_left_hoop_consensus(bundle: dict[str, Path]) -> None:
    signs = basketball_signs(duckdb.connect(), bundle["data"], BB_MATCH)
    got = {(s.period, s.native_team_id): s.attack_sign for s in signs}
    assert got == {(1, BB_HOME): -1, (1, BB_AWAY): 1, (2, BB_HOME): 1, (2, BB_AWAY): -1}
    by_key = {(s.period, s.native_team_id): s.evidence for s in signs}
    assert by_key[(1, BB_HOME)] == "possessions.leftHoop=true in 2/2 possessions"
    assert by_key[(2, BB_AWAY)] == "possessions.leftHoop=true in 1/1 possessions"
    assert all(s.sport == "basketball" and s.native_match_id == BB_MATCH for s in signs)


def test_basketball_signs_reject_a_mixed_period(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_basketball(
        data_dir,
        possessions={
            "id": (pa.string(), ["pos-1", "pos-2", "pos-3", "pos-4"]),
            "period": (pa.int64(), [1, 1, 1, 1]),
            "offTeamId": (pa.int64(), [BB_HOME, BB_HOME, BB_HOME, BB_AWAY]),
            "leftHoop": (pa.bool_(), [True, True, False, False]),
        },
    )
    with pytest.raises(ValueError, match=r"period 1 team 10: leftHoop is true in 2 of 3"):
        basketball_signs(duckdb.connect(), data_dir, BB_MATCH)


def test_basketball_signs_reject_both_teams_on_the_same_hoop(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_basketball(
        data_dir,
        possessions={
            "id": (pa.string(), ["pos-1", "pos-2"]),
            "period": (pa.int64(), [1, 1]),
            "offTeamId": (pa.int64(), [BB_HOME, BB_AWAY]),
            "leftHoop": (pa.bool_(), [True, True]),
        },
    )
    with pytest.raises(ValueError, match=r"period 1: both teams have leftHoop=true"):
        basketball_signs(duckdb.connect(), data_dir, BB_MATCH)


def test_basketball_signs_reject_a_team_outside_the_game(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_basketball(
        data_dir,
        possessions={
            "id": (pa.string(), ["pos-1", "pos-2"]),
            "period": (pa.int64(), [1, 1]),
            "offTeamId": (pa.int64(), [BB_HOME, 99]),
            "leftHoop": (pa.bool_(), [True, False]),
        },
    )
    with pytest.raises(ValueError, match=r"team 99: offTeamId is neither home 10 nor away 20"):
        basketball_signs(duckdb.connect(), data_dir, BB_MATCH)


def test_basketball_shot_probe_counts_every_exclusion(bundle: dict[str, Path]) -> None:
    probe = basketball_shot_probe(duckdb.connect(), bundle["data"], BB_MATCH)
    assert (probe.shots, probe.no_location, probe.no_possession, probe.no_tracking) == (
        7,
        1,
        1,
        1,
    )
    assert probe.matched == 4
    assert probe.rule_closer == 4, "the predicted rotation is the closer one for A, B, C, G"
    assert probe.within == 4, "A, B, C and G sit exactly on the rotated shooter position"
    assert probe.within_flipped == 0, "the opposite rotation matches nothing"
    assert (probe.within_pct, probe.max_ft) == (100.0, 0.0)
    assert probe.residuals == ()
    assert (probe.shots_with_touch, probe.touch_within) == (2, 2)
    verdicts = {(g.period, g.team_id): g.verdict for g in probe.groups}
    assert verdicts == {
        (1, BB_HOME): "ok",
        (1, BB_AWAY): "ok",
        (2, BB_HOME): "ok",
        (2, BB_AWAY): "no_shots",
    }
    home_p1 = next(g for g in probe.groups if (g.period, g.team_id) == (1, BB_HOME))
    assert (home_p1.possessions, home_p1.matched, home_p1.rule_closer) == (2, 2, 2)
    assert (probe.groups_ok, probe.orientation_check) == (3, "ok")


def test_basketball_shot_probe_reports_a_time_offset_residual(bundle: dict[str, Path]) -> None:
    """Shot A's location is 2 ft off the shooter at startFrame but equals the shooter's
    position 10 frames later: a residual of kind time_offset, and the rotation still
    wins, so nothing fails."""
    _write(bundle["data"], "basketball", "events_shots", BB_MATCH, bb_shots(shift_y=2.0))
    later = bb_tracking(a_later=(-30.0, 7.0))
    _write(bundle["data"], "basketball", "tracking_objects", BB_MATCH, later)
    probe = basketball_shot_probe(duckdb.connect(), bundle["data"], BB_MATCH)
    assert (probe.matched, probe.within, probe.within_pct) == (4, 3, 75.0)
    assert probe.max_ft == 2.0 > SHOT_TOL_FT > 1.64
    assert probe.rule_closer == 4 and probe.within_flipped == 0
    assert probe.orientation_check == "ok"
    (res,) = probe.residuals
    assert (res.shot_id, res.kind) == ("s-A", "time_offset")
    assert (res.frame_offset, res.d_at_offset_ft) == (10, 0.0)
    assert res.is_detected and res.d_rule_ft == 2.0
    assert (res.touch_id, res.touch_endloc_to_tracking_ft, res.touch_endloc_to_location_ft) == (
        "t-A",
        0.0,
        2.0,
    ), "the touch's endLoc sits on the tracking, 2 ft from the declared location"


def test_basketball_shot_probe_classifies_an_extrapolated_residual(bundle: dict[str, Path]) -> None:
    _write(bundle["data"], "basketball", "events_shots", BB_MATCH, bb_shots(shift_y=2.0))
    _write(
        bundle["data"],
        "basketball",
        "tracking_objects",
        BB_MATCH,
        bb_tracking(a_detected=False, a_later=(-30.0, 7.0)),
    )
    probe = basketball_shot_probe(duckdb.connect(), bundle["data"], BB_MATCH)
    (res,) = probe.residuals
    assert (res.kind, res.is_detected, res.pred_error_ft) == ("extrapolated", False, 9.0)
    assert res.frame_offset == 10, "the nearby frame is still reported"


def test_basketball_shot_probe_calls_an_unexplained_residual(bundle: dict[str, Path]) -> None:
    """The closest approach of the shooter's track to the declared location is reported
    even when it stays beyond 0.5 m; the shot is then unexplained."""
    _write(bundle["data"], "basketball", "events_shots", BB_MATCH, bb_shots(shift_y=2.0))
    probe = basketball_shot_probe(duckdb.connect(), bundle["data"], BB_MATCH)
    (res,) = probe.residuals
    assert (res.kind, res.frame_offset, res.d_at_offset_ft) == ("unexplained", None, None)

    later = bb_tracking(a_later=(-30.0, 9.0))
    _write(bundle["data"], "basketball", "tracking_objects", BB_MATCH, later)
    probe = basketball_shot_probe(duckdb.connect(), bundle["data"], BB_MATCH)
    (res,) = probe.residuals
    assert (res.kind, res.frame_offset, res.d_at_offset_ft) == ("unexplained", 10, 2.0)


def test_basketball_shot_probe_fails_a_group_when_the_opposite_rotation_hits(
    bundle: dict[str, Path],
) -> None:
    _write(bundle["data"], "basketball", "events_shots", BB_MATCH, bb_shots(flip_a=True))
    probe = basketball_shot_probe(duckdb.connect(), bundle["data"], BB_MATCH)
    home_p1 = next(g for g in probe.groups if (g.period, g.team_id) == (1, BB_HOME))
    assert (home_p1.matched, home_p1.rule_closer, home_p1.within_flipped) == (2, 1, 1)
    assert home_p1.verdict == "FAIL"
    assert probe.orientation_check == "FAIL"
    assert (probe.within, probe.within_flipped) == (3, 1)


def test_fit_three_radius_brackets_the_planted_line() -> None:
    twos = [(d, False) for d in (5.0, 12.5, 18.0, 21.9, 22.0)]
    threes = [(d, True) for d in (22.15, 22.5, 23.4, 24.0, 27.0)]
    fit = fit_three_radius([*twos, *threes])
    assert fit.n == 10
    assert (fit.three_min_ft, fit.two_max_ft) == (22.15, 22.0)
    assert fit.misclassified == 0
    assert fit.plateau_lo_ft == 22.01 and fit.plateau_hi_ft == 22.15
    assert fit.plateau_lo_ft <= FIBA.three_radius_ft <= fit.plateau_hi_ft
    assert not fit.plateau_lo_ft <= NBA.three_radius_ft <= fit.plateau_hi_ft
    assert fit.misclassified_fiba == 0
    assert fit.misclassified_nba == 3, "22.15, 22.5 and 23.4 fall inside an NBA arc"
    assert fit.court == FIBA.spec


def test_fit_three_radius_with_no_threes_decides_nothing() -> None:
    fit = fit_three_radius([(5.0, False), (10.0, False)])
    assert fit.three_min_ft is None
    assert fit.misclassified == fit.misclassified_fiba == fit.misclassified_nba == 0
    assert fit.court == "tie"


# --- football --------------------------------------------------------------------------


def test_football_signs_from_home_team_side_crossed_with_phases(bundle: dict[str, Path]) -> None:
    signs, agree, total = football_signs(duckdb.connect(), bundle["data"], FB_MATCH)
    got = {(s.period, s.native_team_id): s.attack_sign for s in signs}
    assert got == {(1, FB_HOME): -1, (1, FB_AWAY): 1, (2, FB_HOME): 1, (2, FB_AWAY): -1}
    assert (agree, total) == (6, 6)
    by_key = {(s.period, s.native_team_id): s.evidence for s in signs}
    assert by_key[(1, FB_HOME)] == (
        "match.home_team_side[1]=right_to_left (home); "
        "phases_of_play.attacking_side=right_to_left in 2/2 phases"
    )
    assert by_key[(2, FB_AWAY)] == (
        "match.home_team_side[2]=left_to_right (away); "
        "phases_of_play.attacking_side=right_to_left in 2/2 phases"
    )


def test_football_signs_count_a_disagreeing_phase(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_football(
        data_dir,
        phases={
            "period": (pa.int64(), [1, 1, 2]),
            "team_in_possession_id": (pa.int64(), [FB_HOME, FB_HOME, FB_AWAY]),
            "attacking_side": (pa.string(), ["right_to_left", "left_to_right", "right_to_left"]),
        },
    )
    signs, agree, total = football_signs(duckdb.connect(), data_dir, FB_MATCH)
    assert (agree, total) == (2, 3)
    assert {s.attack_sign for s in signs if s.period == 1 and s.native_team_id == FB_HOME} == {
        -1
    }, "the sign still comes from home_team_side; the phase is counted, not voted"


def test_football_signs_reject_a_team_outside_the_match(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_football(
        data_dir,
        phases={
            "period": (pa.int64(), [1]),
            "team_in_possession_id": (pa.int64(), [99]),
            "attacking_side": (pa.string(), ["right_to_left"]),
        },
    )
    with pytest.raises(ValueError, match=r"period 1 team 99: team_in_possession_id is neither"):
        football_signs(duckdb.connect(), data_dir, FB_MATCH)


def test_football_signs_reject_an_unknown_side_value(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_football(
        data_dir,
        phases={
            "period": (pa.int64(), [1]),
            "team_in_possession_id": (pa.int64(), [FB_HOME]),
            "attacking_side": (pa.string(), ["sideways"]),
        },
    )
    with pytest.raises(ValueError, match=r"attacking_side 'sideways'"):
        football_signs(duckdb.connect(), data_dir, FB_MATCH)


def test_football_event_probe_names_the_attack_frame(bundle: dict[str, Path]) -> None:
    probe = football_event_probe(duckdb.connect(), bundle["data"], FB_MATCH)
    assert (probe.events, probe.no_xy, probe.no_tracking, probe.matched) == (5, 1, 1, 3)
    assert probe.attack_within == 3, "every planted event is the rotated tracking position"
    assert probe.venue_within == 1, "only the left_to_right event coincides unrotated"
    assert (probe.attack_pct, probe.venue_pct) == (100.0, 33.33)
    assert probe.attack_max_m == 0.0
    assert probe.winner == "attack"


# --- end to end through the CLI --------------------------------------------------------


def test_cli_writes_table_reports_and_doc(bundle: dict[str, Path]) -> None:
    assert run_cli(bundle) == 0

    table = pq.read_table(orientation_path(bundle["data"]))
    assert table.schema.equals(ORIENTATION_SCHEMA, check_metadata=False)
    rows = table.to_pylist()
    assert len(rows) == 8
    by_period: dict[tuple[str, int, int], list[int]] = {}
    for r in rows:
        by_period.setdefault((r["sport"], r["native_match_id"], r["period"]), []).append(
            r["attack_sign"]
        )
    assert len(by_period) == 4
    for key, signs in by_period.items():
        assert sorted(signs) == [-1, 1], f"{key}: two teams with opposite signs"
    assert table.schema.metadata[b"tracklab.basketball_commit"] == COMMIT.encode()
    evidence = {
        (r["period"], r["native_team_id"]): r["evidence"]
        for r in rows
        if r["sport"] == "basketball"
    }
    assert evidence[(1, BB_HOME)] == (
        "possessions.leftHoop=true in 2/2 possessions; shots closer under this rotation 2/2, "
        "opposite rotation within 0.5 m 0"
    )

    bb = load_report(report_path(bundle["reports"], "basketball"))
    groups = load_report(report_path(bundle["reports"], "basketball_groups"))
    residuals = load_report(report_path(bundle["reports"], "basketball_residual_shots"))
    fb = load_report(report_path(bundle["reports"], "football"))
    assert [r["match_id"] for r in bb] == [str(BB_MATCH)]
    assert [r["match_id"] for r in fb] == [str(FB_MATCH)]
    assert (bb[0]["orientation_check"], bb[0]["groups_ok"]) == ("ok", "3")
    assert bb[0]["groups_no_shots"] == "1"
    assert (bb[0]["shots_within_0_5m_pct"], bb[0]["shots_residual"]) == ("100.0", "0")
    assert (bb[0]["hoop_court"], bb[0]["radius_court"], bb[0]["court"]) == (
        FIBA.spec,
        FIBA.spec,
        FIBA.spec,
    )
    assert [(g["period"], g["team_id"], g["verdict"]) for g in groups] == [
        ("1", "10", "ok"),
        ("1", "20", "ok"),
        ("2", "10", "ok"),
        ("2", "20", "no_shots"),
    ]
    assert residuals == []
    assert (fb[0]["side_check"], fb[0]["phases_agree_pct"]) == ("ok", "100.0")
    assert (fb[0]["event_frame"], fb[0]["players_last_modified"]) == ("attack", "no")

    doc = (bundle["docs"] / "decisions.md").read_text(encoding="utf-8")
    assert doc.startswith("# Decisions\n")
    assert doc.count(DOC_BELOW) == 1 and doc.count(DOC_ABOVE) == 1
    assert f"| {BB_MATCH} |" in doc and f"| {FB_MATCH} |" in doc
    assert "**Orientation consistent in 3 of 4 groups**" in doc
    assert "**Court: `fiba_28x15`** in 1 of 1 matches" in doc
    assert "nobody can assume that `shots.location`" in doc


def test_cli_rewrites_only_its_section_of_the_doc(bundle: dict[str, Path]) -> None:
    doc_path = bundle["docs"] / "decisions.md"
    doc_path.parent.mkdir(parents=True)
    doc_path.write_text(
        f"# Decisions\n\nkeep me above\n\n{DOC_BELOW}\nstale\n{DOC_ABOVE}\n\nkeep me below\n",
        encoding="utf-8",
    )
    assert run_cli(bundle) == 0
    doc = doc_path.read_text(encoding="utf-8")
    assert "keep me above" in doc and "keep me below" in doc
    assert "stale" not in doc
    assert doc.count(DOC_BELOW) == 1 and doc.count(DOC_ABOVE) == 1
    assert doc.index("keep me above") < doc.index(DOC_BELOW) < doc.index(DOC_ABOVE)
    assert doc.index(DOC_ABOVE) < doc.index("keep me below")

    assert run_cli(bundle) == 0
    assert doc_path.read_text(encoding="utf-8") == doc, "a rerun changes nothing"
    assert b"\r\n" not in doc_path.read_bytes(), "LF like the versioned doc, on Windows too"


def test_cli_single_sport_keeps_the_other_sports_rows(bundle: dict[str, Path]) -> None:
    assert run_cli(bundle) == 0
    assert run_cli(bundle, sport="football") == 0
    rows = pq.read_table(orientation_path(bundle["data"])).to_pylist()
    assert sorted({r["sport"] for r in rows}) == ["basketball", "football"]
    assert len(rows) == 8
    doc = (bundle["docs"] / "decisions.md").read_text(encoding="utf-8")
    assert f"| {BB_MATCH} |" in doc, "the doc is rendered from both reports on disk"


def test_cli_publishes_a_residual_as_a_number_and_still_exits_0(bundle: dict[str, Path]) -> None:
    _write(bundle["data"], "basketball", "events_shots", BB_MATCH, bb_shots(shift_y=2.0))
    later = bb_tracking(a_later=(-30.0, 7.0))
    _write(bundle["data"], "basketball", "tracking_objects", BB_MATCH, later)
    assert run_cli(bundle) == 0, "a residual is a number, not a failure"
    bb = load_report(report_path(bundle["reports"], "basketball"))
    assert (bb[0]["orientation_check"], bb[0]["shots_within_0_5m_pct"]) == ("ok", "75.0")
    assert (bb[0]["shots_residual"], bb[0]["shots_residual_time_offset"]) == ("1", "1")
    residuals = load_report(report_path(bundle["reports"], "basketball_residual_shots"))
    assert [(r["shot_id"], r["kind"], r["frame_offset"]) for r in residuals] == [
        ("s-A", "time_offset", "10")
    ]
    doc = (bundle["docs"] / "decisions.md").read_text(encoding="utf-8")
    assert "| s-A |" in doc and "with offsets of +10 frames" in doc


def test_cli_returns_1_when_the_opposite_rotation_hits(bundle: dict[str, Path]) -> None:
    _write(bundle["data"], "basketball", "events_shots", BB_MATCH, bb_shots(flip_a=True))
    assert run_cli(bundle) == 1
    bb = load_report(report_path(bundle["reports"], "basketball"))
    assert (bb[0]["orientation_check"], bb[0]["shots_within_0_5m_flipped"]) == ("FAIL", "1")
    groups = load_report(report_path(bundle["reports"], "basketball_groups"))
    assert [g["verdict"] for g in groups] == ["FAIL", "ok", "ok", "no_shots"]
    assert orientation_path(bundle["data"]).is_file(), "the table is still written"
    doc = (bundle["docs"] / "decisions.md").read_text(encoding="utf-8")
    assert f"**Orientation NOT consistent: 1 of 4 groups fail** ({BB_MATCH} p1 team 10)" in doc
