"""Contracts between the two sports, the z rules and the attack normalisation.

Skipped when silver is not built. Each test prints its figures and files them in
`reports/contracts.json`, written when the module finishes, so a number quoted
anywhere comes from that artefact and not from memory.

The attack check is split by cause on purpose, the fifth time a bar of the plan
has asked two questions at once. "The shooter stands in the attacking half" in
`frames_attacking` depends on the sign being right *and* on `frame_possession`
handing the shot frame to the shooter's team, and on the bundle the second fails
where the first cannot: the view gives 16 shots to the rival (14 sit on the last
frame of their own possession, which the tie-break hands to the rival starting
on it; 2 come after their possession ended), and leaves out 22 whose frame no
possession covers (the provider ends the possession before its own shot, and in
one of them the shooter is not tracked either). Those are counted and pinned.
The sign is judged on the shots the view gives to the shooter's own team,
leaving out the buzzer heaves thrown from the backcourt in the last two seconds
of a period, which are counted too.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest

from tracklab.silver.stats import silver_dir

PIPELINE = Path(__file__).resolve().parents[2]
DATA = PIPELINE / "data"
DUCKDB = DATA / "tracklab.duckdb"
REPORT = PIPELINE / "reports" / "contracts.json"

TABLES = ("dim_sport", "dim_match", "dim_period", "dim_team", "dim_team_period", "dim_entity")
FACTS = ("frames", "events")
VIEWS = ("frame_possession", "frames_attacking")
SPORT_BY_PREFIX = {"bb": "basketball", "fb": "football"}

# Decision 5 keeps in silver only the columns both sports fill. The one known
# exception, documented in its model: basketball publishes no short team name.
FILLED_BY_ONE_SPORT = {("dim_team", "short_name"): "football"}

# The frozen basketball bundle, measured when frames_attacking was built.
SHOTS = 1459
SHOTS_IN_THE_VIEW = 1437
SHOTS_GIVEN_TO_THE_RIVAL = 16
SHOTS_GIVEN_TO_THE_RIVAL_ON_A_BOUNDARY = 14  # the tie-break of frame_possession
BUZZER_S = 2.0
ATTACKING_HALF_PCT = 99.0

pytestmark = pytest.mark.skipif(
    not (silver_dir(DATA) / "frames").is_dir() or not DUCKDB.is_file(),
    reason="silver not built; run dbt build",
)


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    """The dbt database: the two views live only there."""
    return duckdb.connect(str(DUCKDB), read_only=True)


@pytest.fixture(scope="module")
def report() -> Iterator[dict[str, Any]]:
    figures: dict[str, Any] = {}
    yield figures
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(figures, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in con.execute(sql).fetchall()]


def _sport_expr(con: duckdb.DuckDBPyConnection, table: str) -> str:
    """Tables with no `sport` column are split by the prefix of their key."""
    columns = {row[0] for row in _rows(con, f"DESCRIBE {table}")}
    if "sport" in columns:
        return "sport"
    key = "match_id" if "match_id" in columns else "team_id"
    return f"CASE substring({key}, 1, 2) WHEN 'bb' THEN 'basketball' WHEN 'fb' THEN 'football' END"


def test_every_silver_relation_holds_both_sports(
    con: duckdb.DuckDBPyConnection, report: dict[str, Any]
) -> None:
    """At least one row per sport in every table and view silver publishes."""
    counted: dict[str, dict[str, int]] = {}
    for table in TABLES + FACTS + VIEWS:
        rows = _rows(
            con, f"SELECT {_sport_expr(con, table)}, count(*) FROM {table} GROUP BY ALL ORDER BY 1"
        )
        counted[table] = {str(sport): int(n) for sport, n in rows}
        print(f"{table}: {counted[table]}")
    report["rows_by_sport"] = counted
    assert {t: sorted(c) for t, c in counted.items()} == {
        t: ["basketball", "football"] for t in counted
    }
    assert min(n for c in counted.values() for n in c.values()) > 0


def test_the_facts_write_one_schema_for_both_sports(
    con: duckdb.DuckDBPyConnection, report: dict[str, Any]
) -> None:
    """The partitioned facts are written one file per match, so nothing but this
    test stops a sport's files from drifting from the other's. A dimension is one
    file and cannot drift."""
    schemas: dict[str, dict[str, list[list[str]]]] = {}
    for table in FACTS:
        for sport in SPORT_BY_PREFIX.values():
            glob = (silver_dir(DATA) / table / f"sport={sport}" / "**" / "*.parquet").as_posix()
            rows = _rows(
                con,
                "SELECT column_name, column_type "
                f"FROM (DESCRIBE SELECT * FROM read_parquet('{glob}', union_by_name = true))",
            )
            schemas.setdefault(table, {})[sport] = [[str(n), str(t)] for n, t in rows]
        print(f"{table}: {len(schemas[table]['basketball'])} columns in each sport")
    report["fact_columns"] = {t: len(s["basketball"]) for t, s in schemas.items()}
    for table, by_sport in schemas.items():
        assert by_sport["basketball"] == by_sport["football"], table


def test_no_column_is_filled_by_one_sport_only(
    con: duckdb.DuckDBPyConnection, report: dict[str, Any]
) -> None:
    """Decision 5: a column only one sport fills is a sidecar in disguise. The one
    that exists is named above with its reason; a new one fails here."""
    one_sided: dict[tuple[str, str], str] = {}
    for table in TABLES + FACTS:
        columns = [row[0] for row in _rows(con, f"DESCRIBE {table}")]
        filled = ", ".join(f'count("{c}")' for c in columns)
        for sport, *counts in _rows(
            con, f"SELECT {_sport_expr(con, table)}, {filled} FROM {table} GROUP BY ALL ORDER BY 1"
        ):
            for column, n in zip(columns, counts, strict=True):
                if n > 0:
                    one_sided[(table, column)] = (
                        "both" if (table, column) in one_sided else str(sport)
                    )
    found = {key: sport for key, sport in one_sided.items() if sport != "both"}
    print(f"columns filled by one sport only: {found}")
    report["filled_by_one_sport_only"] = {f"{t}.{c}": s for (t, c), s in found.items()}
    assert found == FILLED_BY_ONE_SPORT


def test_players_never_carry_a_z_and_the_ball_share_is_printed(
    con: duckdb.DuckDBPyConnection, report: dict[str, Any]
) -> None:
    """Decision 6. A player's z is NULL in both sports, and the share of ball rows
    with a z is a number per match; that the ball always carries one when it is
    seen is `assert_frames_z_only_on_the_ball`'s verdict, not this test's."""
    players = _rows(
        con,
        "SELECT sport, count(*), count(z_m) FROM frames "
        "WHERE entity_kind = 'player' GROUP BY ALL ORDER BY 1",
    )
    ball = _rows(
        con,
        "SELECT sport, native_match_id, count(*), round(100.0 * count(z_m) / count(*), 3) "
        "FROM frames WHERE entity_kind = 'ball' GROUP BY ALL ORDER BY 1, 2",
    )
    for sport, rows, with_z in players:
        print(f"{sport}: {rows} player rows, {with_z} with a z")
    for sport, match, rows, pct in ball:
        print(f"{sport} {match}: {rows} ball rows, {pct}% with a z")
    report["player_rows_with_z"] = {str(s): int(z) for s, _, z in players}
    report["ball_z_pct"] = {f"{s}:{m}": float(p) for s, m, _, p in ball}
    assert [(s, z) for s, _, z in players] == [("basketball", 0), ("football", 0)]
    assert {s for s, *_ in ball} == {"basketball", "football"}


def test_no_entity_id_belongs_to_two_sports(
    con: duckdb.DuckDBPyConnection, report: dict[str, Any]
) -> None:
    """Decision 4's prefix, checked on the rows rather than on the format."""
    crossing = _rows(
        con,
        """
        SELECT entity_id FROM (
            SELECT entity_id, sport FROM frames
            UNION ALL
            SELECT entity_id, CASE substring(match_id, 1, 2)
                WHEN 'bb' THEN 'basketball' WHEN 'fb' THEN 'football' END
            FROM dim_entity
        )
        GROUP BY 1 HAVING count(DISTINCT sport) > 1
        """,
    )
    print(f"entity ids in two sports: {len(crossing)}")
    report["entity_ids_in_two_sports"] = len(crossing)
    assert crossing == []


def test_every_frame_entity_has_its_row_in_dim_entity(
    con: duckdb.DuckDBPyConnection, report: dict[str, Any]
) -> None:
    """The pair (match, entity), because `bb:ball` is the ball of ten matches."""
    missing = _rows(
        con,
        "SELECT DISTINCT f.match_id, f.entity_id FROM frames f "
        "ANTI JOIN dim_entity e ON e.match_id = f.match_id AND e.entity_id = f.entity_id",
    )
    print(f"frame entities with no dim_entity row: {len(missing)}")
    report["frame_entities_missing_from_dim_entity"] = len(missing)
    assert missing == []


def test_frames_attacking_puts_the_attacked_hoop_at_positive_x(
    con: duckdb.DuckDBPyConnection, report: dict[str, Any]
) -> None:
    """Every basketball shot, placed at its shooter's row of `frames_attacking` in
    its `startFrame`. Per match: the shots, how many the view places, how many
    it gives to the rival, the buzzer heaves, and the share of the rest where the
    shooter stands at x_att_m > 0, with the opposite sign's share beside it. Only
    that share is a verdict: the question is binary and the other sign cannot
    come near the bar."""
    rows = _rows(
        con,
        f"""
        WITH shot AS (
            SELECT e.match_id, e.native_match_id, e.frame_start, e.player_id, e.team_id,
                   e.frame_start = p.frame_end AS on_boundary
            FROM events e
            JOIN events p ON p.event_id = e.possession_id
            WHERE e.sport = 'basketball' AND e.native_family = 'shots'
        ),
        placed AS (
            SELECT s.native_match_id, a.x_att_m, a.clock_s,
                   a.team_in_possession_id = s.team_id AS own_team, s.on_boundary
            FROM shot s
            LEFT JOIN frames_attacking a
              ON a.match_id = s.match_id AND a.frame_native = s.frame_start
             AND a.entity_id = s.player_id
        ),
        judged AS (
            SELECT *, own_team AND clock_s >= {BUZZER_S} AS judged FROM placed
        )
        SELECT native_match_id,
               count(*) AS shots,
               count(x_att_m) AS in_view,
               count(*) FILTER (WHERE NOT own_team) AS to_rival,
               count(*) FILTER (WHERE own_team AND clock_s < {BUZZER_S}) AS buzzer,
               count(*) FILTER (WHERE judged) AS judged,
               round(100.0 * count(*) FILTER (WHERE judged AND x_att_m > 0)
                     / count(*) FILTER (WHERE judged), 2) AS attacking_pct,
               round(100.0 * count(*) FILTER (WHERE judged AND -x_att_m > 0)
                     / count(*) FILTER (WHERE judged), 2) AS flipped_pct,
               count(*) FILTER (WHERE NOT own_team AND on_boundary) AS rival_on_boundary
        FROM judged GROUP BY ALL ORDER BY 1
        """,
    )
    for match, shots, in_view, rival, buzzer, judged, pct, flipped, boundary in rows:
        print(
            f"{match}: {shots} shots, {in_view} in the view, "
            f"{rival} to the rival ({boundary} on their possession's last frame), "
            f"{buzzer} buzzer, {judged} judged: {pct}% at x_att_m > 0, flipped {flipped}%"
        )
    report["shots_attacking_half"] = {
        str(r[0]): {
            "shots": r[1],
            "in_view": r[2],
            "to_rival": r[3],
            "buzzer": r[4],
            "judged": r[5],
            "attacking_pct": float(r[6]),
            "flipped_pct": float(r[7]),
            "to_rival_on_boundary": r[8],
        }
        for r in rows
    }
    assert len(rows) == 10
    assert sum(r[1] for r in rows) == SHOTS
    assert sum(r[2] for r in rows) == SHOTS_IN_THE_VIEW
    assert sum(r[3] for r in rows) == SHOTS_GIVEN_TO_THE_RIVAL
    assert sum(r[8] for r in rows) == SHOTS_GIVEN_TO_THE_RIVAL_ON_A_BOUNDARY
    assert min(float(r[6]) for r in rows) >= ATTACKING_HALF_PCT
