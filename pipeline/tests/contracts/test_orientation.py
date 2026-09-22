"""Contract of the orientation probe against the artefacts `tracklab orientation` wrote:
the table `bronze.common.orientation` and the per-match, per-group and per-residual-shot
reports.

Skipped when the artefacts are not built. Every figure is read from the Parquet or the
CSV on disk with DuckDB or the csv module, never recomputed from the probe's own code,
and printed per match or per group, never as an aggregate. The two "recomputed from
bronze" tests derive the signs again with their own SQL over the bronze tables, so the
table is checked by a second path that shares nothing with `silver.orientation`. The
orientation assertion is binary per group with no threshold; the share within 0.5 m is
printed as a number; the residual shots are pinned to the literal count and
classification measured on the frozen bundle, so a regression has to change them on
purpose.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from tracklab.ingest.manifest import load_manifest
from tracklab.silver.orientation import (
    FIBA,
    ORIENTATION_SCHEMA,
    load_report,
    orientation_path,
    report_path,
)

PIPELINE = Path(__file__).resolve().parents[2]
DATA = PIPELINE / "data"
BRONZE = DATA / "bronze"
REPORTS = PIPELINE / "reports"
TABLE = orientation_path(DATA)
REPORT = {
    name: report_path(REPORTS, name)
    for name in ("basketball", "basketball_groups", "basketball_residual_shots", "football")
}
EXPECTED_ROWS = {"basketball": 82, "football": 80}  # 9 x 4 + 1 x 5 periods, 20 x 2; x 2 teams
EXPECTED_GROUPS = 82
# Measured on the frozen bundle (commit 4bbed2e3...): of the 1,433 shots with a location,
# a possession and a shooter position at startFrame, 10 lie more than 0.5 m from the
# rotated shooter position. 2 are extrapolated positions (isDetected false), 7 are found
# within 0.5 m of the shooter at another frame of the tracking (the frame of closest
# approach within 100 frames), at these offsets (frames at 25 fps, both signs), and 1
# (shot-114169-4-139) is found at no frame: its closest approach is 1.85 ft at -4 frames.
EXPECTED_MATCHED = 1433
EXPECTED_RESIDUAL = 10
EXPECTED_EXTRAPOLATED = 2
EXPECTED_OFFSETS = [-14, -7, 8, 20, 20, 31, 33]
EXPECTED_UNEXPLAINED = ["shot-114169-4-139"]

pytestmark = pytest.mark.skipif(
    not (TABLE.is_file() and all(p.is_file() for p in REPORT.values())),
    reason="run `tracklab orientation` first",
)


def _match_ids(sport: str) -> list[int]:
    source_id = {"basketball": "opendata-basketball", "football": "opendata-football"}[sport]
    source = load_manifest(PIPELINE / "manifest" / "sources.json").source(source_id)
    return sorted({f.match_id for f in source.files if f.role == "tracking" and f.match_id})


def test_table_schema_and_rows_per_sport() -> None:
    assert pq.read_schema(TABLE).equals(ORIENTATION_SCHEMA, check_metadata=False)
    con = duckdb.connect()
    counts = dict(
        con.execute(
            "SELECT sport, count(*) FROM read_parquet(?) GROUP BY 1 ORDER BY 1", [TABLE.as_posix()]
        ).fetchall()
    )
    print(f"\norientation rows per sport: {counts}")
    assert counts == EXPECTED_ROWS


def test_two_teams_with_opposite_signs_in_every_period() -> None:
    con = duckdb.connect()
    rows = con.execute(
        "SELECT sport, native_match_id, count(DISTINCT period), "
        "count(*) FILTER (WHERE bad) "
        "FROM (SELECT sport, native_match_id, period, "
        "      count(*) != 2 OR count(DISTINCT native_team_id) != 2 OR sum(attack_sign) != 0 "
        "      OR count(*) FILTER (WHERE attack_sign NOT IN (-1, 1)) > 0 AS bad "
        "      FROM read_parquet(?) GROUP BY ALL) "
        "GROUP BY ALL ORDER BY 1, 2",
        [TABLE.as_posix()],
    ).fetchall()
    print(f"\n{'sport':>10} {'match_id':>8} {'periods':>7} {'bad_periods':>11}")
    violations = []
    for sport, match_id, periods, bad in rows:
        print(f"{sport:>10} {match_id:>8} {periods:>7} {bad:>11}")
        if bad:
            violations.append((sport, match_id))
    assert violations == []
    assert len(rows) == 30


def test_basketball_signs_equal_left_hoop_recomputed_from_bronze() -> None:
    """Own SQL over `events_possessions`: the sign is -1 when every possession of the
    team in the period has `leftHoop`, +1 when none has; the table must say the same."""
    con = duckdb.connect()
    recomputed = con.execute(
        "SELECT match_id, period, offTeamId, bool_and(leftHoop), bool_or(leftHoop), count(*) "
        "FROM read_parquet(?) GROUP BY ALL ORDER BY 1, 2, 3",
        [(BRONZE / "basketball" / "events_possessions" / "*.parquet").as_posix()],
    ).fetchall()
    expected = {}
    for match_id, period, team, all_left, any_left, n in recomputed:
        assert all_left == any_left, f"{match_id} p{period} team {team}: mixed leftHoop in {n}"
        expected[(match_id, period, team)] = -1 if all_left else 1
    table = {
        (m, p, t): s
        for m, p, t, s in con.execute(
            "SELECT native_match_id, period, native_team_id, attack_sign FROM read_parquet(?) "
            "WHERE sport = 'basketball'",
            [TABLE.as_posix()],
        ).fetchall()
    }
    print(f"\nbasketball (match, period, team) groups recomputed: {len(expected)}")
    for match_id in _match_ids("basketball"):
        n = sum(1 for k in expected if k[0] == match_id)
        print(f"{match_id}: {n} groups")
    assert table == expected


def test_football_signs_equal_home_team_side_recomputed_from_bronze() -> None:
    con = duckdb.connect()
    expected = {}
    for match_id, home, away, sides in con.execute(
        "SELECT match_id, home_team_id, away_team_id, home_team_side FROM read_parquet(?)",
        [(BRONZE / "football" / "match" / "*.parquet").as_posix()],
    ).fetchall():
        for period, side in enumerate(sides, start=1):
            home_sign = 1 if side == "left_to_right" else -1
            expected[(match_id, period, home)] = home_sign
            expected[(match_id, period, away)] = -home_sign
    table = {
        (m, p, t): s
        for m, p, t, s in con.execute(
            "SELECT native_match_id, period, native_team_id, attack_sign FROM read_parquet(?) "
            "WHERE sport = 'football'",
            [TABLE.as_posix()],
        ).fetchall()
    }
    print(f"\nfootball (match, period, team) groups recomputed: {len(expected)}")
    assert table == expected


def test_reports_have_one_row_per_match() -> None:
    for sport in ("basketball", "football"):
        rows = load_report(REPORT[sport])
        ids = [int(r["match_id"]) for r in rows]
        print(f"\n{sport}: {len(rows)} rows, {len(rows[0])} columns")
        assert ids == _match_ids(sport)


def test_basketball_rotation_wins_in_every_group() -> None:
    """Binary, per (match, period, team), no threshold: the rotation `leftHoop` predicts
    is the closer one for every matched shot and the opposite lands within 0.5 m of none."""
    groups = load_report(REPORT["basketball_groups"])
    print(
        f"\n{'match_id':>8} {'p':>2} {'team':>5} {'left':>5} {'sign':>4} {'poss':>4} "
        f"{'matched':>7} {'closer':>6} {'within':>6} {'flipped':>7} {'median':>6} {'verdict':>8}"
    )
    bad = []
    for g in groups:
        print(
            f"{g['match_id']:>8} {g['period']:>2} {g['team_id']:>5} {g['left_hoop']:>5} "
            f"{g['attack_sign']:>4} {g['possessions']:>4} {g['shots_matched']:>7} "
            f"{g['shots_rule_closer']:>6} {g['shots_within_0_5m']:>6} "
            f"{g['shots_within_0_5m_flipped']:>7} {g['shot_median_ft']:>6} {g['verdict']:>8}"
        )
        if g["verdict"] != "ok":
            bad.append((g["match_id"], g["period"], g["team_id"], g["verdict"]))
        assert g["shots_rule_closer"] == g["shots_matched"]
        assert g["shots_within_0_5m_flipped"] == "0"
    assert len(groups) == EXPECTED_GROUPS
    assert bad == [], f"groups where the rotation does not win outright: {bad}"
    assert sum(int(g["shots_matched"]) for g in groups) == EXPECTED_MATCHED


def test_basketball_share_within_half_metre_is_a_number_per_match() -> None:
    rows = load_report(REPORT["basketball"])
    print(
        f"\n{'match_id':>8} {'matched':>7} {'closer':>6} {'within':>6} {'pct':>6} "
        f"{'flipped':>7} {'median':>6} {'p95':>6} {'max':>6} {'residual':>8}"
    )
    for r in rows:
        print(
            f"{r['match_id']:>8} {r['shots_matched']:>7} {r['shots_rule_closer']:>6} "
            f"{r['shots_within_0_5m']:>6} {r['shots_within_0_5m_pct']:>6} "
            f"{r['shots_within_0_5m_flipped']:>7} {r['shot_median_ft']:>6} "
            f"{r['shot_p95_ft']:>6} {r['shot_max_ft']:>6} {r['shots_residual']:>8}"
        )
        assert r["left_hoop_consensus"] == "ok"
        assert r["orientation_check"] == "ok"
        assert r["shots_within_0_5m_flipped"] == "0"
        assert 0.0 <= float(r["shots_within_0_5m_pct"]) <= 100.0
        assert float(r["shot_median_ft"]) < 0.01, "median residual of the rule is ~0 ft"
        assert int(r["shots_matched"]) - int(r["shots_within_0_5m"]) == int(r["shots_residual"])


def test_basketball_residual_shots_are_pinned() -> None:
    """10 of 1,433: 2 extrapolated, 7 found at another frame with offsets of both signs, 1
    found nowhere; in every one with a touch, its endLoc sits on the tracking, not on
    shots.location."""
    residuals = load_report(REPORT["basketball_residual_shots"])
    print(
        f"\n{'match_id':>8} {'shot_id':>20} {'d_rule':>6} {'det':>5} {'predErr':>7} "
        f"{'kind':>12} {'offset':>6} {'d_off':>6} {'touch->trk':>10} {'touch->loc':>10}"
    )
    for r in residuals:
        print(
            f"{r['match_id']:>8} {r['shot_id']:>20} {r['d_rule_ft']:>6} {r['is_detected']:>5} "
            f"{r['pred_error_ft']:>7} {r['kind']:>12} {r['frame_offset']:>6} "
            f"{r['d_at_offset_ft']:>6} {r['touch_endloc_to_tracking_ft']:>10} "
            f"{r['touch_endloc_to_location_ft']:>10}"
        )
    assert len(residuals) == EXPECTED_RESIDUAL
    kinds = [r["kind"] for r in residuals]
    assert kinds.count("extrapolated") == EXPECTED_EXTRAPOLATED
    assert [r["shot_id"] for r in residuals if r["kind"] == "unexplained"] == EXPECTED_UNEXPLAINED
    offsets = sorted(int(r["frame_offset"]) for r in residuals if r["kind"] == "time_offset")
    assert offsets == EXPECTED_OFFSETS
    assert min(offsets) < 0 < max(offsets), "both signs: not a release-frame effect"
    for r in residuals:
        if r["touch_id"] == "":
            continue
        assert float(r["touch_endloc_to_tracking_ft"]) == 0.0, r["shot_id"]
        assert float(r["touch_endloc_to_location_ft"]) == float(r["d_rule_ft"]), r["shot_id"]
    matches = load_report(REPORT["basketball"])
    assert sum(int(r["shots_residual"]) for r in matches) == EXPECTED_RESIDUAL


def test_basketball_court_is_fiba_in_every_match() -> None:
    rows = load_report(REPORT["basketball"])
    print(
        f"\n{'match_id':>8} {'hoop_x':>8} {'res_fiba':>8} {'res_nba':>8} "
        f"{'three_min':>9} {'two_max':>8} {'mis_fiba':>8} {'mis_nba':>7} {'court':>11}"
    )
    for r in rows:
        print(
            f"{r['match_id']:>8} {r['hoop_x_median_ft']:>8} {r['dist_resid_max_fiba_ft']:>8} "
            f"{r['dist_resid_max_nba_ft']:>8} {r['radius_three_min_ft']:>9} "
            f"{r['radius_two_max_ft']:>8} {r['radius_misclassified_fiba']:>8} "
            f"{r['radius_misclassified_nba']:>7} {r['court']:>11}"
        )
    assert all(r["court"] == FIBA.spec for r in rows)
    assert all(float(r["dist_resid_max_fiba_ft"]) < float(r["dist_resid_max_nba_ft"]) for r in rows)


def test_football_sides_agree_with_phases_in_every_match() -> None:
    rows = load_report(REPORT["football"])
    print(f"\n{'match_id':>8} {'home_team_side':>27} {'phases':>6} {'agree':>5} {'pct':>5}")
    for r in rows:
        print(
            f"{r['match_id']:>8} {r['home_team_side']:>27} {r['phases']:>6} "
            f"{r['phases_agree']:>5} {r['phases_agree_pct']:>5}"
        )
    assert all(r["side_check"] == "ok" and float(r["phases_agree_pct"]) == 100.0 for r in rows)


def test_football_attack_frame_wins_in_every_match() -> None:
    rows = load_report(REPORT["football"])
    print(f"\n{'match_id':>8} {'matched':>7} {'venue_1m':>8} {'attack_1m':>9} {'median_m':>8}")
    for r in rows:
        print(
            f"{r['match_id']:>8} {r['pp_matched']:>7} {r['venue_within_1m_pct']:>8} "
            f"{r['attack_within_1m_pct']:>9} {r['attack_median_m']:>8}"
        )
        assert r["event_frame"] == "attack"
        assert float(r["attack_within_1m_pct"]) > float(r["venue_within_1m_pct"])


def test_football_event_regime_coincides_with_players_last_modified() -> None:
    """The matches whose events equal the tracking exactly are the matches whose
    players[] carry last_modified: two independent signals, one cut."""
    rows = load_report(REPORT["football"])
    print(f"\n{'match_id':>8} {'last_modified':>13} {'attack_1m':>9} {'median_m':>8} {'max_m':>7}")
    exact, with_lm = set(), set()
    for r in rows:
        print(
            f"{r['match_id']:>8} {r['players_last_modified']:>13} {r['attack_within_1m_pct']:>9} "
            f"{r['attack_median_m']:>8} {r['attack_max_m']:>7}"
        )
        if float(r["attack_median_m"]) == 0.0:
            exact.add(r["match_id"])
        if r["players_last_modified"] == "yes":
            with_lm.add(r["match_id"])
    assert len(exact) == 10 and len(with_lm) == 10
    assert exact == with_lm
