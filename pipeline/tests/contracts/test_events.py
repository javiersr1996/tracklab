"""Contract of `events` and `frame_possession` against what dbt wrote.

Skipped when they are not built. Counts are pinned to the frozen bundles, the
cross-checks are rebuilt from bronze with this file's own SQL, and the three
places where the provider contradicts itself are counted and pinned rather than
asserted away: a possession that starts before its own period, two that overlap
their neighbour, and 29 that last a single frame.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tracklab.silver.stats import silver_dir

PIPELINE = Path(__file__).resolve().parents[2]
DATA = PIPELINE / "data"
BRONZE = DATA / "bronze"
DUCKDB = DATA / "tracklab.duckdb"

EVENT_TYPES = {
    "basketball": {
        "possession": 1564,
        "player_possession": 6662,
        "pass": 4786,
        "shot": 1889,
        "other": 57083,
    },
    "football": {
        "possession": 4009,  # 3,998 chains, 11 of them split at half time
        "player_possession": 2638,
        "pass": 16072,
        "other": 84485,
    },
}
# The provider's own inconsistencies, measured on the frozen basketball bundle.
EVENTS_OUTSIDE_THEIR_PERIOD = 4  # 2 possessions and the 2 chances that follow them
OVERLAPPING_NATIVE_POSSESSIONS = 2
SINGLE_FRAME_POSSESSIONS = 29
FRAMES_CLAIMED_ACROSS_PERIODS = 429  # all of them in match 178442

pytestmark = pytest.mark.skipif(
    not (silver_dir(DATA) / "events").is_dir() or not DUCKDB.is_file(),
    reason="events not built; run dbt build",
)


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    """The dbt database, for the view, plus bronze read straight from Parquet."""
    connection = duckdb.connect(str(DUCKDB), read_only=True)
    for sport, table in (
        ("basketball", "events_possessions"),
        ("basketball", "events_shots"),
        ("basketball", "tracking_objects"),
        ("football", "dynamic_events"),
        ("football", "tracking_frames"),
        ("football", "match"),
    ):
        glob = (BRONZE / sport / table / "*.parquet").as_posix()
        connection.execute(
            f"CREATE OR REPLACE TEMP VIEW bronze_{sport}_{table} AS "
            f"SELECT * FROM read_parquet('{glob}')"
        )
    return connection


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[object, ...]]:
    return [tuple(row) for row in con.execute(sql).fetchall()]


def test_the_conformed_vocabulary_holds_both_sports(con: duckdb.DuckDBPyConnection) -> None:
    """A conformed type is one both sports can answer. `shot` is the exception the
    plan already documents: football delivers no shot event, it marks a player
    possession that ended in one."""
    rows = _rows(con, "SELECT sport, event_type, count(*) FROM events GROUP BY ALL ORDER BY 1, 2")
    counted: dict[str, dict[str, int]] = {}
    for sport, event_type, n in rows:
        counted.setdefault(str(sport), {})[str(event_type)] = int(n)
    for sport, types in counted.items():
        print(f"{sport}: {types}")
    assert counted == EVENT_TYPES
    assert "shot" not in counted["football"]


def test_every_event_id_is_unique_and_prefixed(con: duckdb.DuckDBPyConnection) -> None:
    rows = _rows(
        con,
        "SELECT sport, count(*), count(DISTINCT event_id), "
        "count(*) FILTER (WHERE substring(event_id, 1, 3) NOT IN ('bb:', 'fb:')) "
        "FROM events GROUP BY ALL ORDER BY 1",
    )
    for row in rows:
        print(f"{row[0]}: {row[1]} rows, {row[2]} ids, {row[3]} unprefixed")
    assert all(row[1] == row[2] and row[3] == 0 for row in rows)


def test_basketball_possessions_are_the_native_ones_match_by_match(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """The acceptance's check, and the cheapest proof that no family was lost or
    duplicated on the way in."""
    rows = _rows(
        con,
        """
        WITH silver AS (
            SELECT native_match_id, count(*) AS n
            FROM events WHERE sport = 'basketball' AND event_type = 'possession' GROUP BY ALL
        ),
        native AS (
            SELECT match_id AS native_match_id, count(*) AS n
            FROM bronze_basketball_events_possessions GROUP BY ALL
        )
        SELECT n.native_match_id, n.n, s.n FROM native n
        JOIN silver s USING (native_match_id) ORDER BY 1
        """,
    )
    for row in rows:
        print(f"{row[0]}: native {row[1]}, silver {row[2]}")
    assert len(rows) == 10
    assert [row for row in rows if row[1] != row[2]] == []


def test_football_possessions_never_overlap_and_cover_what_the_provider_claims(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Per match: how many possessions the chain rule made, and how much of what
    the tracking itself attributes to a team they cover. The denominator is the
    provider's own attribution and not every in-play frame, because the provider
    names an owner for only 71.25% of them; asking a derivation to cover 90% of
    the rest would be asking it to invent one."""
    rows = _rows(
        con,
        """
        WITH provider AS (
            SELECT t.match_id, t.frame,
                   CASE t.possession_group
                       WHEN 'home team' THEN m.home_team_id
                       WHEN 'away team' THEN m.away_team_id
                   END AS team_id
            FROM bronze_football_tracking_frames t
            JOIN bronze_football_match m ON m.id = t.match_id
            WHERE t.period IS NOT NULL AND t.ball_x IS NOT NULL
              AND t.possession_group IS NOT NULL
        ),
        possessions AS (
            SELECT native_match_id, event_id, team_id, frame_start, frame_end
            FROM events WHERE sport = 'football' AND event_type = 'possession'
        ),
        covered AS (
            SELECT p.match_id, p.frame, p.team_id AS provider_team,
                   min_by(q.team_id, q.frame_start) AS rule_team
            FROM provider p
            LEFT JOIN possessions q
              ON q.native_match_id = p.match_id AND p.frame BETWEEN q.frame_start AND q.frame_end
            GROUP BY ALL
        ),
        scored AS (
            SELECT match_id, count(*) AS provider_frames,
                   count(*) FILTER (WHERE rule_team IS NOT NULL) AS covered,
                   count(*) FILTER (WHERE rule_team = 'fb:' || provider_team) AS agree
            FROM covered GROUP BY ALL
        ),
        counted AS (
            SELECT native_match_id AS match_id, count(*) AS possessions
            FROM possessions GROUP BY ALL
        ),
        neighboured AS (
            SELECT native_match_id AS match_id, frame_start,
                   lag(frame_end) OVER (PARTITION BY native_match_id ORDER BY frame_start) AS prev
            FROM possessions
        ),
        stepped_on AS (
            SELECT match_id, count(*) FILTER (WHERE frame_start <= prev) AS overlapping
            FROM neighboured GROUP BY ALL
        )
        SELECT s.match_id, c.possessions, s.provider_frames,
               round(100.0 * s.covered / s.provider_frames, 2),
               round(100.0 * s.agree / nullif(s.covered, 0), 2),
               o.overlapping
        FROM scored s JOIN counted c USING (match_id) JOIN stepped_on o USING (match_id)
        ORDER BY 1
        """,
    )
    for row in rows:
        print(f"{row[0]}: {row[1]} possessions, {row[3]}% of provider frames, agree {row[4]}%")
    assert len(rows) == 20
    assert sum(int(str(row[1])) for row in rows) == EVENT_TYPES["football"]["possession"]
    assert [row for row in rows if row[5] != 0] == []
    assert min(float(str(row[3])) for row in rows) > 70.0


def test_events_start_inside_their_period_except_where_the_provider_says_otherwise(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Two basketball possessions, and the two chances that hang off them, carry a
    period label the tracking disagrees with: one starts 18 frames after period 4
    stops being tracked, the other 1,450 frames before period 4 begins. Pinned
    rather than asserted to zero, because the bundle says four."""
    rows = _rows(
        con,
        """
        SELECT e.sport, e.match_id, e.native_family, e.event_id, e.frame_start,
               p.frame_native_start, p.frame_native_end
        FROM events e
        JOIN dim_period p ON p.match_id = e.match_id AND p.period = e.period
        WHERE e.frame_start IS NOT NULL
          AND (e.frame_start < p.frame_native_start OR e.frame_start > p.frame_native_end)
        ORDER BY 2, 3
        """,
    )
    for row in rows:
        print(f"{row[1]} {row[2]} {row[3]}: frame {row[4]} outside [{row[5]}, {row[6]}]")
    assert len(rows) == EVENTS_OUTSIDE_THEIR_PERIOD
    assert {str(row[0]) for row in rows} == {"basketball"}


def test_football_possessions_end_inside_their_own_period(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """A derived possession is one period's: the chain rule opens a new one at the
    break even when the provider does not flag it. 11 chains crossed half time
    before that rule, carrying the first half's period and attacking side into the
    second (final review of the plan, row V)."""
    rows = _rows(
        con,
        """
        SELECT e.match_id, e.event_id, e.period, e.frame_start, e.frame_end, p.frame_native_end
        FROM events e
        JOIN dim_period p ON p.match_id = e.match_id AND p.period = e.period
        WHERE e.sport = 'football' AND e.event_type = 'possession'
          AND e.frame_end > p.frame_native_end
        ORDER BY 1, 2
        """,
    )
    for row in rows:
        print(f"{row[0]} {row[1]} period {row[2]}: frames {row[3]}-{row[4]}, period ends {row[5]}")
    assert rows == []


def test_frame_possession_gives_each_frame_one_possession(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """True by construction, so what is worth measuring is the ties the view broke:
    how many frames two possessions claimed, and how many of those were not the
    shared boundary that both bundles use."""
    duplicated = _rows(
        con,
        "SELECT count(*) FROM (SELECT match_id, frame_native, count(*) AS n "
        "FROM frame_possession GROUP BY ALL HAVING n > 1)",
    )
    ties = _rows(
        con,
        """
        WITH claims AS (
            SELECT f.sport, f.match_id, f.frame_native, count(*) AS n,
                   count(*) FILTER (WHERE e.frame_start = f.frame_native) AS starting_here
            FROM (SELECT DISTINCT sport, match_id, frame_native FROM frames) f
            JOIN events e
              ON e.match_id = f.match_id AND e.event_type = 'possession'
              AND f.frame_native BETWEEN e.frame_start AND e.frame_end
            GROUP BY ALL
        )
        SELECT sport, count(*) FILTER (WHERE n > 1) AS claimed_twice,
               count(*) FILTER (WHERE n > 1 AND starting_here = 0) AS not_a_boundary,
               max(n) AS most_claims
        FROM claims GROUP BY ALL ORDER BY 1
        """,
    )
    for row in ties:
        print(f"{row[0]}: {row[1]} frames claimed twice, {row[2]} of them not a boundary")
    assert duplicated == [(0,)]
    by_sport = {str(row[0]): row for row in ties}
    assert by_sport["football"][1] == 0
    assert by_sport["basketball"][2] == FRAMES_CLAIMED_ACROSS_PERIODS


def test_the_native_possessions_of_basketball_carry_their_own_defects(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Counted from bronze, so the numbers the view's tie-break absorbs stay
    visible instead of becoming a property of silver."""
    rows = _rows(
        con,
        """
        WITH ordered AS (
            SELECT match_id, startFrame, endFrame,
                   lag(endFrame) OVER (PARTITION BY match_id ORDER BY startFrame, endFrame) AS prev
            FROM bronze_basketball_events_possessions
        )
        SELECT count(*) FILTER (WHERE prev IS NOT NULL AND startFrame < prev) AS overlapping,
               count(*) FILTER (WHERE prev IS NOT NULL AND startFrame = prev) AS sharing_a_boundary,
               count(*) FILTER (WHERE endFrame = startFrame) AS single_frame,
               count(*) AS possessions
        FROM ordered
        """,
    )
    print(
        f"native basketball possessions: overlapping {rows[0][0]}, boundary {rows[0][1]}, "
        f"single frame {rows[0][2]}, total {rows[0][3]}"
    )
    assert rows[0][0] == OVERLAPPING_NATIVE_POSSESSIONS
    assert rows[0][2] == SINGLE_FRAME_POSSESSIONS


def test_event_coordinates_land_on_the_surface(con: duckdb.DuckDBPyConnection) -> None:
    """The cheap check that the rotation and the unit are right: a 180-degree error
    keeps a point on the surface, but a missing rotation puts the basketball events
    of half the periods on the wrong side, and a missing foot-to-metre conversion
    puts them off the court entirely."""
    rows = _rows(
        con,
        """
        SELECT e.sport, count(*) AS with_coordinates,
               round(100.0 * count(*) FILTER (
                   WHERE abs(e.x_start_m) <= m.surface_length_m / 2 + 3
                     AND abs(e.y_start_m) <= m.surface_width_m / 2 + 3) / count(*), 3) AS inside_pct
        FROM events e JOIN dim_match m ON m.match_id = e.match_id
        WHERE e.x_start_m IS NOT NULL GROUP BY ALL ORDER BY 1
        """,
    )
    for row in rows:
        print(f"{row[0]}: {row[1]} events with coordinates, {row[2]}% on the surface")
    assert min(float(str(row[2])) for row in rows) >= 99.0


def test_the_basketball_rotation_reaches_the_table_and_not_just_the_probe(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Task 9 proved which rotation maps the events into the venue frame; this
    proves `events` applied it. For every shot with a shooter position at its
    `startFrame`, the rotation in the table must be closer to that position than
    the opposite one, and the opposite one must land within 0.5 m of no shot at
    all. A 180-degree error keeps a point on the court, so nothing weaker than a
    comparison against the tracking can catch one."""
    rows = _rows(
        con,
        """
        WITH shot AS (
            SELECT e.native_match_id, e.native_event_id, e.x_start_m, e.y_start_m
            FROM events e
            WHERE e.sport = 'basketball' AND e.native_family = 'shots'
              AND e.x_start_m IS NOT NULL
        ),
        placed AS (
            SELECT s.native_match_id,
                   sqrt(pow(s.x_start_m - t.x * 0.3048, 2)
                        + pow(s.y_start_m - t.y * 0.3048, 2)) AS d_rule,
                   sqrt(pow(s.x_start_m + t.x * 0.3048, 2)
                        + pow(s.y_start_m + t.y * 0.3048, 2)) AS d_flipped
            FROM shot s
            JOIN bronze_basketball_events_shots b
              ON b.match_id = s.native_match_id AND b.id = s.native_event_id
            JOIN bronze_basketball_tracking_objects t
              ON t.match_id = s.native_match_id AND t.frameIdx = b.startFrame
             AND t.playerId = b.shooterId
        )
        SELECT native_match_id, count(*) AS matched,
               count(*) FILTER (WHERE d_rule < d_flipped) AS rule_closer,
               count(*) FILTER (WHERE d_flipped <= 0.5) AS flipped_within_half_a_metre,
               round(median(d_rule), 3) AS median_m
        FROM placed GROUP BY ALL ORDER BY 1
        """,
    )
    for row in rows:
        print(
            f"{row[0]}: {row[1]} shots, rule closer {row[2]}, flipped within 0.5 m {row[3]}, "
            f"median {row[4]} m"
        )
    assert len(rows) == 10
    assert [row for row in rows if row[1] != row[2]] == []
    assert [row for row in rows if row[3] != 0] == []
