"""Contract of `frames` against the Parquet dbt wrote, one match at a time.

Skipped when the table is not built. The row counts are rebuilt from bronze with
this file's own SQL and compared match by match, printing the three numbers the
acceptance asks for: what bronze offers, what the boundary rules exclude and what
silver holds.

The surface check is split by `is_detected` on purpose. Mixing the two asks two
questions at once, which is the mistake task 9 already paid for: a position the
provider extrapolated wanders off the pitch by design, and a share that mixes it
with seen positions can neither pass nor fail for a reason anyone can name. The
detected share answers the question that matters here (are these metres, in the
venue frame), the extrapolated one is printed as a number.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tracklab.silver.stats import silver_dir, table_glob, table_path

PIPELINE = Path(__file__).resolve().parents[2]
DATA = PIPELINE / "data"
BRONZE = DATA / "bronze"
FRAMES = silver_dir(DATA) / "frames"

MATCHES = {"basketball": 10, "football": 20}
ROWS = {"basketball": 9_126_744, "football": 20_213_849}
# The margin the schema allows around a surface before a position is called odd.
MARGIN_M = 3.0
DETECTED_INSIDE_PCT = 99.9

pytestmark = pytest.mark.skipif(
    not FRAMES.is_dir() or not table_path(DATA, "dim_match").is_file(),
    reason="frames not built; run dbt build --select frames",
)


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    for table in ("frames", "dim_match", "dim_sport"):
        connection.execute(
            f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{table_glob(DATA, table)}')"
        )
    for sport, table in (
        ("basketball", "tracking_objects"),
        ("basketball", "tracking_frames"),
        ("football", "tracking_objects"),
        ("football", "tracking_frames"),
    ):
        glob = (BRONZE / sport / table / "*.parquet").as_posix()
        connection.execute(
            f"CREATE VIEW bronze_{sport}_{table} AS SELECT * FROM read_parquet('{glob}')"
        )
    return connection


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[object, ...]]:
    return [tuple(row) for row in con.execute(sql).fetchall()]


def test_one_partition_per_match_on_disk(con: duckdb.DuckDBPyConnection) -> None:
    """The layout the acceptance asks for: sport, then match, then one file."""
    partitions = sorted(p.relative_to(FRAMES).as_posix() for p in FRAMES.glob("*/*"))
    files = sorted(p.parent.relative_to(FRAMES).as_posix() for p in FRAMES.glob("*/*/*.parquet"))
    by_sport: dict[str, int] = {}
    for partition in partitions:
        sport = partition.split("/")[0].removeprefix("sport=")
        by_sport[sport] = by_sport.get(sport, 0) + 1
    print(f"partitions: {by_sport}, files: {len(files)}")
    assert by_sport == MATCHES
    assert files == partitions  # exactly one file in each


def test_row_counts_against_bronze_match_by_match(con: duckdb.DuckDBPyConnection) -> None:
    """Three numbers per match: what bronze offers as a candidate row, what the
    boundary rules take out, and what silver holds. A basketball candidate is a
    `tracking_objects` row; a football one is a `tracking_objects` row plus one
    ball per frame, since that provider keeps the ball in `tracking_frames`."""
    rows = _rows(
        con,
        """
        WITH candidates AS (
            SELECT 'basketball' AS sport, o.match_id AS native_match_id,
                   count(*) AS bronze_rows,
                   count(*) FILTER (WHERE f.period IS NULL) AS excluded
            FROM bronze_basketball_tracking_objects o
            JOIN bronze_basketball_tracking_frames f
              ON f.match_id = o.match_id AND f.frameIdx = o.frameIdx
            GROUP BY ALL
            UNION ALL
            SELECT 'football', o.match_id, count(*), count(*) FILTER (WHERE f.period IS NULL)
            FROM bronze_football_tracking_objects o
            JOIN bronze_football_tracking_frames f
              ON f.match_id = o.match_id AND f.frame = o.frame
            GROUP BY ALL
            UNION ALL
            SELECT 'football', f.match_id, count(*),
                   count(*) FILTER (WHERE f.period IS NULL OR f.ball_x IS NULL)
            FROM bronze_football_tracking_frames f
            GROUP BY ALL
        ),
        bronze AS (
            SELECT sport, native_match_id,
                   sum(bronze_rows) AS bronze_rows, sum(excluded) AS excluded
            FROM candidates GROUP BY ALL
        ),
        silver AS (
            SELECT sport, native_match_id, count(*) AS silver_rows FROM frames GROUP BY ALL
        )
        SELECT b.sport, b.native_match_id, b.bronze_rows, b.excluded, s.silver_rows,
               b.bronze_rows - b.excluded - s.silver_rows AS unexplained
        FROM bronze b JOIN silver s USING (sport, native_match_id)
        ORDER BY 1, 2
        """,
    )
    for row in rows:
        print(f"{row[0]} {row[1]}: bronze {row[2]} - excluded {row[3]} = silver {row[4]}")
    assert len(rows) == sum(MATCHES.values())
    assert [row for row in rows if row[5] != 0] == []


def test_totals_per_sport(con: duckdb.DuckDBPyConnection) -> None:
    rows = dict(_rows(con, "SELECT sport, count(*) FROM frames GROUP BY ALL ORDER BY 1"))
    print(f"frames: {rows} (total {sum(rows.values())})")
    assert rows == ROWS


def test_the_two_sports_have_the_same_columns_and_types(con: duckdb.DuckDBPyConnection) -> None:
    """One schema, two sports: the claim the whole platform rests on, read off the
    files each sport actually wrote rather than off the model."""
    schemas = {}
    for sport in MATCHES:
        glob = (FRAMES / f"sport={sport}" / "**" / "*.parquet").as_posix()
        schemas[sport] = _rows(
            con,
            f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_parquet('{glob}'))",
        )
    for sport, columns in schemas.items():
        print(f"{sport}: {len(columns)} columns")
    assert schemas["basketball"] == schemas["football"]
    assert [name for name, _ in schemas["basketball"]] == [
        "match_id",
        "period",
        "frame_native",
        "t_ms",
        "clock_s",
        "entity_id",
        "entity_kind",
        "team_id",
        "x_m",
        "y_m",
        "z_m",
        "is_detected",
        "native_match_id",
        "sport",
    ]


def test_positions_sit_on_the_surface_when_the_provider_saw_them(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Per match, the share of positions within the surface plus a 3 m margin,
    detected and extrapolated apart. A wrong unit or a wrong origin cannot pass
    the detected column: basketball left in feet would put |x| out to 57 m on a
    28 m court."""
    rows = _rows(
        con,
        f"""
        WITH tagged AS (
            SELECT f.sport, f.native_match_id, f.is_detected,
                   abs(f.x_m) <= m.surface_length_m / 2 + {MARGIN_M}
                   AND abs(f.y_m) <= m.surface_width_m / 2 + {MARGIN_M} AS inside
            FROM frames f JOIN dim_match m ON m.match_id = f.match_id
        )
        SELECT sport, native_match_id,
               count(*) FILTER (WHERE is_detected) AS detected,
               round(100.0 * count(*) FILTER (WHERE is_detected AND inside)
                     / count(*) FILTER (WHERE is_detected), 4) AS detected_inside_pct,
               count(*) FILTER (WHERE NOT is_detected) AS extrapolated,
               round(100.0 * count(*) FILTER (WHERE NOT is_detected AND inside)
                     / count(*) FILTER (WHERE NOT is_detected), 4) AS extrapolated_inside_pct
        FROM tagged GROUP BY ALL ORDER BY 1, 2
        """,
    )
    for row in rows:
        print(f"{row[0]} {row[1]}: detected {row[2]} {row[3]}%, extrapolated {row[4]} {row[5]}%")
    worst_detected = min(float(str(row[3])) for row in rows)
    worst_extrapolated = min(float(str(row[5])) for row in rows)
    print(f"worst detected {worst_detected}%, worst extrapolated {worst_extrapolated}%")
    assert len(rows) == sum(MATCHES.values())
    assert worst_detected >= DETECTED_INSIDE_PCT


def test_t_ms_is_the_frame_counter_at_the_sports_own_rate(con: duckdb.DuckDBPyConnection) -> None:
    """Derived again from dim_sport rather than trusted: t_ms = frame x 1000 / hz,
    exact in both sports, so no frame is ever placed by rounding."""
    wrong = _rows(
        con,
        "SELECT f.sport, count(*) FROM frames f JOIN dim_sport s ON s.sport = f.sport "
        "WHERE f.t_ms <> f.frame_native * 1000 / s.sample_rate_hz GROUP BY ALL",
    )
    spread = _rows(con, "SELECT sport, min(t_ms), max(t_ms) FROM frames GROUP BY ALL ORDER BY 1")
    print(f"t_ms range: {spread}, rows off the rate: {len(wrong)}")
    assert wrong == []


def test_the_clock_keeps_each_sports_own_semantics(con: duckdb.DuckDBPyConnection) -> None:
    """Decision 3: a clock that stops and a clock that runs are not conformed, they
    are labelled. Basketball counts down inside [0, 600]; football counts up from
    0 and runs past 2700 s because stoppage time is played."""
    rows = _rows(
        con,
        "SELECT sport, round(min(clock_s), 1), round(max(clock_s), 1), "
        "count(*) FILTER (WHERE clock_s IS NULL) FROM frames GROUP BY ALL ORDER BY 1",
    )
    for row in rows:
        print(f"{row[0]}: clock_s {row[1]} to {row[2]}, {row[3]} null")
    basketball, football = rows
    assert basketball[1] >= 0.0 and basketball[2] <= 600.0
    assert football[1] >= 0.0 and football[2] > 2700.0
    assert basketball[3] == 0 and football[3] == 0
