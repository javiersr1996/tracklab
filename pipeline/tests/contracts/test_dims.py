"""Contract of the six dimensions against the Parquet `dbt build --select tag:dims` wrote.

Skipped when silver is not built. Every figure is read from disk and printed, and
the cross-checks derive their side of the comparison from bronze with their own
SQL, so a dimension is never checked against the model that produced it. The
counts are pinned to what the frozen bundles hold (10 basketball matches, 20
football), so a change has to be made on purpose.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tracklab.silver.stats import table_path

PIPELINE = Path(__file__).resolve().parents[2]
DATA = PIPELINE / "data"
BRONZE = DATA / "bronze"
TABLES = ("dim_sport", "dim_match", "dim_period", "dim_team", "dim_team_period", "dim_entity")

# The frozen bundles: 10 ACB matches and 20 A-League matches (the football bundle
# turned out to hold 20, not the 10 the plan was first written against).
MATCHES = {"basketball": 10, "football": 20}
PERIODS = {"basketball": 41, "football": 40}  # 9 x 4 + 1 x 5 (one overtime), 20 x 2
TEAMS = {"basketball": 17, "football": 13}
TEAM_PERIODS = {"basketball": 82, "football": 80}
SPORT_BY_PREFIX = {"bb": "basketball", "fb": "football"}

pytestmark = pytest.mark.skipif(
    not all(table_path(DATA, t).is_file() for t in TABLES),
    reason="silver dimensions not built; run dbt build --select tag:dims",
)


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    for table in TABLES:
        path = table_path(DATA, table).as_posix()
        connection.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{path}')")
    for sport, table in (
        ("basketball", "matches"),
        ("basketball", "tracking_objects"),
        ("football", "match"),
        ("football", "tracking_objects"),
    ):
        glob = (BRONZE / sport / table / "*.parquet").as_posix()
        connection.execute(
            f"CREATE VIEW bronze_{sport}_{table} AS SELECT * FROM read_parquet('{glob}')"
        )
    return connection


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[object, ...]]:
    return [tuple(row) for row in con.execute(sql).fetchall()]


def _by_sport(con: duckdb.DuckDBPyConnection, table: str, column: str) -> dict[str, int]:
    rows = _rows(con, f"SELECT {column}, count(*) FROM {table} GROUP BY ALL ORDER BY 1")
    return {SPORT_BY_PREFIX.get(str(key), str(key)): int(n) for key, n in rows}  # type: ignore[arg-type]


def test_dim_sport_holds_the_two_measured_rows(con: duckdb.DuckDBPyConnection) -> None:
    rows = _rows(
        con,
        "SELECT sport, id_prefix, native_unit, unit_to_m, sample_rate_hz, clock_kind, "
        "players_on_surface, native_event_frame FROM dim_sport ORDER BY sport",
    )
    for row in rows:
        print(row)
    assert rows == [
        ("basketball", "bb", "ft", 0.3048, 25, "countdown", 10, "attacking_neg_x"),
        ("football", "fb", "m", 1.0, 10, "elapsed", 22, "attacking_pos_x"),
    ]


def test_row_counts_per_sport(con: duckdb.DuckDBPyConnection) -> None:
    for table, expected in (("dim_match", MATCHES), ("dim_team", TEAMS)):
        counted = _by_sport(con, table, "sport")
        print(f"{table}: {counted} (total {sum(counted.values())})")
        assert counted == expected

    for table, expected in (("dim_period", PERIODS), ("dim_team_period", TEAM_PERIODS)):
        counted = _by_sport(con, table, "substring(match_id, 1, 2)")
        print(f"{table}: {counted} (total {sum(counted.values())})")
        assert counted == expected


def test_n_periods_is_what_dim_period_holds(con: duckdb.DuckDBPyConnection) -> None:
    """dim_match declares nothing it does not count: the two models are compared
    match by match rather than trusted."""
    disagree = _rows(
        con,
        "SELECT m.match_id, m.n_periods, count(p.period) FROM dim_match m "
        "LEFT JOIN dim_period p ON p.match_id = m.match_id GROUP BY ALL "
        "HAVING m.n_periods <> count(p.period)",
    )
    spread = _rows(
        con, "SELECT sport, min(n_periods), max(n_periods) FROM dim_match GROUP BY ALL ORDER BY 1"
    )
    print(f"periods per match (sport, min, max): {spread}")
    assert disagree == []


def test_regulation_seconds_are_the_three_the_competitions_give(
    con: duckdb.DuckDBPyConnection,
) -> None:
    rows = _rows(con, "SELECT regulation_s, count(*) FROM dim_period GROUP BY ALL ORDER BY 1")
    print(f"regulation_s: {rows}")
    assert rows == [(300, 1), (600, 40), (2700, 40)]


def test_every_period_has_two_teams_with_opposite_signs(con: duckdb.DuckDBPyConnection) -> None:
    """The same assertion as the dbt singular test, over the written Parquet
    instead of over the model, and it prints the groups it checked."""
    groups = _rows(
        con,
        "SELECT count(*), min(n), max(n), min(s), max(s) FROM ("
        "  SELECT count(*) AS n, sum(attack_sign) AS s FROM dim_team_period "
        "  GROUP BY match_id, period)",
    )
    print(f"(match, period) groups, teams min/max, sign sum min/max: {groups}")
    assert groups == [(81, 2, 2, 0, 0)]


def test_exactly_one_ball_per_match_and_the_rest_are_players(
    con: duckdb.DuckDBPyConnection,
) -> None:
    kinds = dict(_rows(con, "SELECT entity_kind, count(*) FROM dim_entity GROUP BY ALL ORDER BY 1"))
    wrong = _rows(
        con,
        "SELECT count(*) FROM (SELECT match_id, count(*) FILTER (WHERE entity_kind = 'ball') AS n "
        "FROM dim_entity GROUP BY match_id HAVING n <> 1)",
    )
    print(f"dim_entity: {kinds}, matches without exactly one ball: {wrong[0][0]}")
    assert kinds["ball"] == sum(MATCHES.values())
    assert wrong == [(0,)]


def test_every_tracked_object_has_a_row_in_dim_entity(con: duckdb.DuckDBPyConnection) -> None:
    """The guarantee task 11 builds `frames` on: no tracking id can turn up that
    the dimension does not know. Its side is derived from bronze with its own SQL."""
    missing = _rows(
        con,
        """
        WITH tracked AS (
            SELECT DISTINCT 'bb:' || match_id AS match_id, 'bb:' || playerId AS entity_id
            FROM bronze_basketball_tracking_objects WHERE side <> 'ball'
            UNION ALL
            SELECT DISTINCT 'fb:' || match_id, 'fb:' || player_id
            FROM bronze_football_tracking_objects
        )
        SELECT t.match_id, t.entity_id FROM tracked t
        LEFT JOIN dim_entity e ON e.match_id = t.match_id AND e.entity_id = t.entity_id
        WHERE e.entity_id IS NULL
        """,
    )
    players = _by_sport(con, "dim_entity WHERE entity_kind = 'player'", "substring(match_id, 1, 2)")
    print(f"dim_entity players: {players}, tracked ids with no row: {len(missing)}")
    assert missing == []


def test_football_surface_is_the_pitch_its_own_match_json_declares(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Three pitch lengths live in this bundle, so a constant here would have
    looked right and been wrong in 10 matches of the 20."""
    disagree = _rows(
        con,
        "SELECT m.match_id, m.surface_length_m, b.pitch_length, m.surface_width_m, b.pitch_width "
        "FROM dim_match m JOIN bronze_football_match b ON 'fb:' || b.id = m.match_id "
        "WHERE m.surface_length_m <> b.pitch_length OR m.surface_width_m <> b.pitch_width",
    )
    spread = _rows(
        con,
        "SELECT surface_spec, count(*) FROM dim_match WHERE sport = 'football' "
        "GROUP BY ALL ORDER BY 1",
    )
    print(f"football pitches: {spread}")
    assert disagree == []


def test_basketball_surface_is_the_court_task_9_measured(con: duckdb.DuckDBPyConnection) -> None:
    rows = _rows(
        con,
        "SELECT surface_spec, surface_length_m, surface_width_m, count(*) FROM dim_match "
        "WHERE sport = 'basketball' GROUP BY ALL ORDER BY 1",
    )
    print(f"basketball courts: {rows}")
    assert rows == [("fiba_28x15", 28.0, 15.0, MATCHES["basketball"])]


def test_every_key_carries_its_sport_prefix(con: duckdb.DuckDBPyConnection) -> None:
    """Decision 4: no silver key is a native integer, in any dimension."""
    offenders = []
    for table, columns in (
        ("dim_match", ("match_id", "home_team_id", "away_team_id")),
        ("dim_period", ("match_id",)),
        ("dim_team", ("team_id",)),
        ("dim_team_period", ("match_id", "team_id")),
        ("dim_entity", ("match_id", "entity_id", "team_id", "canonical_player_id")),
    ):
        for column in columns:
            rows = _rows(
                con,
                f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL "
                f"AND substring({column}, 1, 3) NOT IN ('bb:', 'fb:')",
            )
            print(f"{table}.{column}: {rows[0][0]} unprefixed")
            if rows[0][0]:
                offenders.append((table, column, rows[0][0]))
    assert offenders == []
