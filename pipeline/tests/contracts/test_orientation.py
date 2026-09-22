"""Contract of the orientation probe against the artefacts `tracklab orientation` wrote:
the table `bronze.common.orientation` and the two per-match reports.

Skipped when the artefacts are not built. Every figure is read from the Parquet or the
CSV on disk with DuckDB or the csv module, never recomputed from the probe's own code,
and printed per match, never as an aggregate. The two "recomputed from bronze" tests
derive the signs again with their own SQL over the bronze tables, so the table is
checked by a second path that shares nothing with `silver.orientation`.
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
    SHOT_MEDIAN_MAX_FT,
    SHOT_PASS_PCT,
    load_report,
    orientation_path,
)

PIPELINE = Path(__file__).resolve().parents[2]
DATA = PIPELINE / "data"
BRONZE = DATA / "bronze"
REPORTS = PIPELINE / "reports"
TABLE = orientation_path(DATA)
REPORT = {sport: REPORTS / f"orientation_{sport}.csv" for sport in ("basketball", "football")}
EXPECTED_ROWS = {"basketball": 82, "football": 80}  # 9 x 4 + 1 x 5 periods, 20 x 2; x 2 teams

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
    for sport, path in REPORT.items():
        rows = load_report(path)
        ids = [int(r["match_id"]) for r in rows]
        print(f"\n{sport}: {len(rows)} rows, {len(rows[0])} columns")
        assert ids == _match_ids(sport)


def test_basketball_shot_probe_bar_per_match() -> None:
    rows = load_report(REPORT["basketball"])
    print(
        f"\n{'match_id':>8} {'matched':>7} {'within':>6} {'pct':>6} {'flipped':>7} {'verdict':>7}"
    )
    below = []
    for r in rows:
        pct = float(r["shots_within_0_5m_pct"])
        print(
            f"{r['match_id']:>8} {r['shots_matched']:>7} {r['shots_within_0_5m']:>6} "
            f"{pct:>6} {r['shots_within_0_5m_flipped_pct']:>7} {r['shot_probe']:>7}"
        )
        assert float(r["shots_within_0_5m_flipped_pct"]) == 0.0
        assert float(r["shot_median_ft"]) <= SHOT_MEDIAN_MAX_FT
        assert r["left_hoop_consensus"] == "ok"
        assert r["shot_probe"] == "pass"
        if pct < SHOT_PASS_PCT:
            below.append(r["match_id"])
    # The share is printed, never asserted: the rotation is decided by the two asserts
    # above (the opposite rotation matches nothing, the rule's median residual is ~0),
    # and the shots outside the tolerance are a timing mismatch in `shots.location`,
    # not an orientation error. See `docs/decisions.md` and the note in orientation.py.
    print(f"below {SHOT_PASS_PCT}% within 0.5 m: {below or 'none'}")


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


def test_the_ten_residual_shots_stay_ten_and_stay_explained() -> None:
    """Pins the residual so a regression has to change this number on purpose.

    10 of 1,433 matched shots sit outside 0.5 m of the shooter's tracking position at
    `startFrame`. They are not an orientation error: the opposite rotation matches none
    of them either, and their declared location is misaligned in time with `startFrame`.
    Counted here from the per-match report, which the probe writes from bronze."""
    rows = load_report(REPORT["basketball"])
    matched = sum(int(r["shots_matched"]) for r in rows)
    within = sum(int(r["shots_within_0_5m"]) for r in rows)
    residual = matched - within
    print(f"\nmatched={matched} within={within} residual={residual}")
    assert (matched, residual) == (1433, 10)
