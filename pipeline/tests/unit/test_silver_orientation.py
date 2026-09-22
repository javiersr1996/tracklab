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


def bb_shots(shift_y: float = 0.0, mirror: bool = False) -> Columns:
    """Seven shots: A, B, C, G match the planted tracking; D has no shooter position at
    its frame, E no location, F a possession id that does not exist.

    ``shift_y`` moves shot A's declared location away from its shooter: one displaced
    location, which is a provider mismatch and not a wrong rotation. ``mirror`` negates
    every location, which is what a wrong rotation actually looks like: the opposite
    rotation becomes the one that matches. ``distance`` keeps the unmirrored geometry
    so the court fit stays out of the way of the probe under test."""
    xs = [-30.0, -30.0, -25.0, -20.0, None, -10.0, -18.0]
    ys = [5.0 + shift_y, 5.0, 0.0, -3.0, None, 0.0, 0.0]
    dist = [None if x is None else _dist(x, y) for x, y in zip(xs, ys, strict=True)]
    if mirror:
        xs = [None if x is None else -x for x in xs]
        ys = [None if y is None else -y for y in ys]
    return {
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
    }


def write_basketball(data_dir: Path, possessions: Columns | None = None) -> None:
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
    _write(data_dir, "basketball", "events_shots", BB_MATCH, bb_shots())
    _write(
        data_dir,
        "basketball",
        "tracking_objects",
        BB_MATCH,
        {
            "frameIdx": (pa.int64(), [100, 200, 300, 500, 600, 700]),
            "playerId": (pa.int64(), [101, 201, 101, 101, 101, 101]),
            "x": (pa.float64(), [-30.0, 30.0, 25.0, -12.0, -10.0, -18.0]),
            "y": (pa.float64(), [5.0, -5.0, 0.0, 1.0, 0.0, 0.0]),
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
    assert probe.within == 4, "A, B, C and G sit exactly on the rotated shooter position"
    assert probe.within_flipped == 0, "the opposite rotation matches nothing"
    assert probe.within_pct == 100.0
    assert probe.max_ft == 0.0
    assert probe.verdict == "pass"


def test_basketball_shot_probe_counts_a_shifted_location_but_does_not_call_it_a_flip(
    bundle: dict[str, Path],
) -> None:
    """One location away from its shooter is a provider mismatch, not a wrong rotation:
    it is counted and reported, and the verdict stays `pass` because the opposite
    rotation still matches nothing and the median residual is still 0. This is the real
    bundle's case, where 10 shots of 1,433 sit outside the tolerance."""
    _write(bundle["data"], "basketball", "events_shots", BB_MATCH, bb_shots(shift_y=2.0))
    probe = basketball_shot_probe(duckdb.connect(), bundle["data"], BB_MATCH)
    assert probe.matched == 4
    assert probe.within == 3, "shot A is now 2 ft from the shooter, beyond 0.5 m"
    assert probe.within_pct == 75.0
    assert probe.max_ft == 2.0
    assert 2.0 > SHOT_TOL_FT > 1.64
    assert probe.within_flipped == 0
    assert probe.median_ft <= SHOT_TOL_FT
    assert probe.verdict == "pass"


def test_basketball_shot_probe_fails_when_the_opposite_rotation_is_the_matching_one(
    bundle: dict[str, Path],
) -> None:
    """What a wrong rotation looks like, and what the bar exists to catch: every
    location mirrored, so the rule matches nothing and the opposite matches everything."""
    _write(bundle["data"], "basketball", "events_shots", BB_MATCH, bb_shots(mirror=True))
    probe = basketball_shot_probe(duckdb.connect(), bundle["data"], BB_MATCH)
    assert probe.matched == 4
    assert probe.within == 0
    assert probe.within_flipped == probe.matched
    assert probe.median_ft > SHOT_TOL_FT
    assert probe.verdict == "FAIL"


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

    bb = load_report(bundle["reports"] / "orientation_basketball.csv")
    fb = load_report(bundle["reports"] / "orientation_football.csv")
    assert [r["match_id"] for r in bb] == [str(BB_MATCH)]
    assert [r["match_id"] for r in fb] == [str(FB_MATCH)]
    assert (bb[0]["shot_probe"], bb[0]["shots_within_0_5m_pct"]) == ("pass", "100.0")
    assert (bb[0]["hoop_court"], bb[0]["radius_court"], bb[0]["court"]) == (
        FIBA.spec,
        FIBA.spec,
        FIBA.spec,
    )
    assert (fb[0]["side_check"], fb[0]["phases_agree_pct"]) == ("ok", "100.0")
    assert (fb[0]["event_frame"], fb[0]["players_last_modified"]) == ("attack", "no")

    doc = (bundle["docs"] / "decisions.md").read_text(encoding="utf-8")
    assert doc.startswith("# Decisions\n")
    assert doc.count(DOC_BELOW) == 1 and doc.count(DOC_ABOVE) == 1
    assert f"| {BB_MATCH} |" in doc and f"| {FB_MATCH} |" in doc
    assert "**Court: `fiba_28x15`** in 1 of 1 matches" in doc


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


def test_cli_single_sport_keeps_the_other_sports_rows(bundle: dict[str, Path]) -> None:
    assert run_cli(bundle) == 0
    assert run_cli(bundle, sport="football") == 0
    rows = pq.read_table(orientation_path(bundle["data"])).to_pylist()
    assert sorted({r["sport"] for r in rows}) == ["basketball", "football"]
    assert len(rows) == 8
    doc = (bundle["docs"] / "decisions.md").read_text(encoding="utf-8")
    assert f"| {BB_MATCH} |" in doc, "the doc is rendered from both reports on disk"


def test_cli_returns_1_when_the_rotation_is_the_wrong_one(bundle: dict[str, Path]) -> None:
    _write(bundle["data"], "basketball", "events_shots", BB_MATCH, bb_shots(mirror=True))
    assert run_cli(bundle) == 1
    bb = load_report(bundle["reports"] / "orientation_basketball.csv")
    assert (bb[0]["shot_probe"], bb[0]["shots_within_0_5m_pct"]) == ("FAIL", "0.0")
    assert bb[0]["shots_within_0_5m_flipped_pct"] == "100.0"
    assert orientation_path(bundle["data"]).is_file(), "the table is still written"


def test_cli_returns_0_and_reports_the_share_when_only_a_location_is_displaced(
    bundle: dict[str, Path],
) -> None:
    """The run succeeds, and the share below the plan's original 99% is still written
    down: reported as a number, never as a verdict."""
    _write(bundle["data"], "basketball", "events_shots", BB_MATCH, bb_shots(shift_y=2.0))
    assert run_cli(bundle) == 0
    bb = load_report(bundle["reports"] / "orientation_basketball.csv")
    assert (bb[0]["shot_probe"], bb[0]["shots_within_0_5m_pct"]) == ("pass", "75.0")
    doc = (bundle["docs"] / "decisions.md").read_text(encoding="utf-8")
    assert f"the plan first asked for in {BB_MATCH}" in doc
