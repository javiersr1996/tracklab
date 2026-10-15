"""Contract of the gold season-aggregate models against the Parquet `dbt build` wrote (task 40).

Skipped when gold is not built. The expected figures come from bronze with their own
SQL (`count(col)` per numeric column, no UNPIVOT), never from the model that is being
checked. Runs on `data_root()`: the real bundle or the CI fixtures.
"""

from __future__ import annotations

import duckdb
import pytest

from tracklab.paths import data_root

WIDE = {
    ("basketball", "shots"): "agg_bb_shots",
    ("basketball", "drives"): "agg_bb_drives",
    ("basketball", "picks"): "agg_bb_picks",
    ("football", "obr"): "agg_fb_obr",
    ("football", "passing"): "agg_fb_passing",
    ("football", "physical"): "agg_fb_physical",
}
GOLD = (*WIDE.values(), "dim_player", "dim_season_team", "dim_metric", "fact_player_season_metric")
IDS = {
    "competition_edition_id",
    "competition_id",
    "season_id",
    "player_id",
    "team_id",
    "source_row",
}

pytestmark = pytest.mark.skipif(
    not all(_p.is_file() for _p in (data_root() / "gold" / t / "data.parquet" for t in GOLD)),
    reason="gold not built; run dbt build --select gold",
)


def _gold(table: str) -> str:
    return f"read_parquet('{(data_root() / 'gold' / table / 'data.parquet').as_posix()}')"


def _bronze(sport: str, family: str) -> str:
    path = data_root() / "bronze" / sport / f"aggregates_{family}" / "data.parquet"
    return f"read_parquet('{path.as_posix()}')"


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def _numeric_columns(con: duckdb.DuckDBPyConnection, sport: str, family: str) -> list[str]:
    described = con.execute(f"DESCRIBE SELECT * FROM {_bronze(sport, family)}").fetchall()
    return [n for n, t, *_ in described if t in ("BIGINT", "DOUBLE") and n not in IDS]


def _non_null_cells(
    con: duckdb.DuckDBPyConnection, sport: str, family: str, where: str = "true"
) -> int:
    cols = _numeric_columns(con, sport, family)
    counts = " + ".join(f'count("{c}")' for c in cols)
    row = con.execute(f"SELECT {counts} FROM {_bronze(sport, family)} WHERE {where}").fetchone()
    assert row is not None
    return int(row[0])


def test_the_fact_has_one_row_per_non_null_numeric_cell(con: duckdb.DuckDBPyConnection) -> None:
    per_table = {k: _non_null_cells(con, *k) for k in WIDE}
    (rows,) = con.execute(f"SELECT count(*) FROM {_gold('fact_player_season_metric')}").fetchone()  # type: ignore[misc]
    by_family = dict(
        con.execute(
            f"SELECT sport || '/' || family, count(*) FROM {_gold('fact_player_season_metric')} "
            "GROUP BY 1"
        ).fetchall()
    )
    print(f"\nnon-null cells by bronze table: {per_table}")
    print(f"fact_player_season_metric rows={rows} (hypothesis of the plan: 366962)")
    assert rows == sum(per_table.values())
    assert by_family == {f"{s}/{f}": n for (s, f), n in per_table.items()}


def test_the_wide_models_keep_every_bronze_row(con: duckdb.DuckDBPyConnection) -> None:
    for (sport, family), model in WIDE.items():
        (bronze,) = con.execute(f"SELECT count(*) FROM {_bronze(sport, family)}").fetchone()  # type: ignore[misc]
        (gold,) = con.execute(f"SELECT count(*) FROM {_gold(model)}").fetchone()  # type: ignore[misc]
        print(f"\n{model}: bronze={bronze} gold={gold}")
        assert gold == bronze


@pytest.mark.parametrize("family", ["shots", "drives", "picks"])
def test_a_traded_basketball_player_is_not_counted_twice(
    con: duckdb.DuckDBPyConnection, family: str
) -> None:
    """The provider's `total` row repeats the sum of a traded player's team rows, so a
    sum over every row counts that player twice. Per player, the fact without the
    total rows must add up to what bronze says on the team rows, and the total rows
    in the fact must be exactly the bronze rows named `total`."""
    fact = _gold("fact_player_season_metric")
    bronze = _bronze("basketball", family)
    metric = "attempts" if family == "shots" else "games_played"
    (total_cells,) = con.execute(
        f"SELECT count(*) FROM {fact} WHERE sport = 'basketball' AND family = '{family}' "
        "AND is_season_total"
    ).fetchone()  # type: ignore[misc]
    assert total_cells == _non_null_cells(con, "basketball", family, "team_name = 'total'")
    assert total_cells > 0

    rows = con.execute(
        f"""
        WITH f AS (
            SELECT player_id, sum(value) FILTER (WHERE NOT is_season_total) AS teams,
                   sum(value) FILTER (WHERE is_season_total) AS total
            FROM {fact}
            WHERE sport = 'basketball' AND family = '{family}' AND metric = '{metric}'
            GROUP BY player_id
        ),
        b AS (
            SELECT player_id, sum("{metric}") FILTER (WHERE team_name <> 'total') AS teams,
                   sum("{metric}") FILTER (WHERE team_name = 'total') AS total
            FROM {bronze} GROUP BY player_id
        )
        SELECT f.player_id, f.teams, b.teams, f.total, b.total
        FROM f JOIN b USING (player_id)
        WHERE f.teams IS DISTINCT FROM b.teams OR f.total IS DISTINCT FROM b.total
        """
    ).fetchall()
    traded = con.execute(f"SELECT count(*) FROM {bronze} WHERE team_name = 'total'").fetchone()
    print(f"\nbasketball/{family}: traded players={traded}, mismatches={rows}")
    assert rows == []


def test_the_season_total_is_not_a_team(con: duckdb.DuckDBPyConnection) -> None:
    (n,) = con.execute(
        f"SELECT count(*) FROM {_gold('dim_season_team')} "
        "WHERE team_id IS NULL OR team_name = 'total'"
    ).fetchone()  # type: ignore[misc]
    assert n == 0


def test_each_player_has_one_name_per_sport(con: duckdb.DuckDBPyConnection) -> None:
    """`dim_player` takes `max(player_name)`: that is only honest if no player carries two."""
    union = " UNION ALL ".join(
        f"SELECT '{s}' AS sport, player_id, player_name FROM {_bronze(s, f)}" for s, f in WIDE
    )
    (conflicts,) = con.execute(
        f"SELECT count(*) FROM (SELECT 1 FROM ({union}) GROUP BY sport, player_id "
        "HAVING count(DISTINCT player_name) > 1)"
    ).fetchone()  # type: ignore[misc]
    assert conflicts == 0


def test_dim_metric_kinds_cover_every_metric(con: duckdb.DuckDBPyConnection) -> None:
    kinds = con.execute(
        f"SELECT kind, count(*) FROM {_gold('dim_metric')} GROUP BY kind ORDER BY kind"
    ).fetchall()
    cols = sum(len(_numeric_columns(con, s, f)) for s, f in WIDE)
    print(f"\ndim_metric kinds: {kinds} (numeric columns in bronze: {cols})")
    assert sum(n for _, n in kinds) == cols


# Read off bronze (min-max in the comment): none of these can be added up, so none is a `count`.
NOT_COUNTS = {
    ("physical", "psv99"): "speed",  # 24.3 to 32.3, km/h
    ("physical", "psv99_top5"): "speed",
    ("physical", "timetohsr_top3"): "time",  # 0.57 to 1.02, seconds
    ("physical", "timetosprint_top3"): "time",
    ("physical", "total_metersperminute_full_all"): "speed",  # 96.13 to 140.61, m/min
    ("physical", "total_metersperminute_full_tip"): "speed",
    ("physical", "total_metersperminute_full_otip"): "speed",
    ("passing", "pass_avgxpass_attempted"): "percentage",  # 58.14 to 96.4
    ("passing", "pass_avgxpass_torun_attempted"): "percentage",
    ("physical", "hsr_count_full_all"): "count",  # 27 means per match, 3 season totals: all counts
}


def test_dim_metric_does_not_call_a_speed_a_time_or_a_percentage_a_count(
    con: duckdb.DuckDBPyConnection,
) -> None:
    kinds = {
        (f, m): k
        for f, m, k in con.execute(
            f"SELECT family, metric, kind FROM {_gold('dim_metric')}"
        ).fetchall()
    }
    assert {key: kinds[key] for key in NOT_COUNTS} == NOT_COUNTS


def test_percentage_is_0_to_100_and_fraction_is_0_to_1(con: duckdb.DuckDBPyConnection) -> None:
    """The two scales never share a kind: football passes are 0-100, basketball shares 0-1."""
    rows = con.execute(
        f"SELECT d.kind, d.sport, min(f.value), max(f.value) "
        f"FROM {_gold('dim_metric')} d JOIN {_gold('fact_player_season_metric')} f "
        "USING (sport, family, metric) WHERE d.kind IN ('percentage', 'fraction') "
        "GROUP BY ALL ORDER BY ALL"
    ).fetchall()
    print(f"\nscales: {rows}")
    # `uncontested_efg_percentage` reaches 1.5: a fraction can pass 1, but never 2.
    limits = {"fraction": ("basketball", 0.0, 2.0), "percentage": ("football", 1.5, 100.0)}
    for kind, sport, low, high in rows:
        want_sport, floor, ceiling = limits[kind]
        assert sport == want_sport
        assert low >= 0
        assert high <= ceiling
        if kind == "percentage":
            assert high > floor  # a 0-1 scale would not reach this
    assert {r[0] for r in rows} <= set(limits)


def test_bronze_has_no_numeric_type_the_unpivot_would_skip(con: duckdb.DuckDBPyConnection) -> None:
    """Model and `_numeric_columns` both take BIGINT and DOUBLE; a third type would vanish."""
    types = {
        t
        for s, f in WIDE
        for _, t, *_ in con.execute(f"DESCRIBE SELECT * FROM {_bronze(s, f)}").fetchall()
    }
    print(f"\nbronze column types: {sorted(types)}")
    assert types <= {"VARCHAR", "BIGINT", "DOUBLE", "DATE"}
