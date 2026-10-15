"""Grain of the six bronze season aggregates, measured on the Parquet on disk (task 39).

The key is what the probe measured, not what the provider's README says:
football repeats (`player_id`, `team_id`) once per `position_group`, and basketball
adds a season-total row (`team_name = 'total'`, null `team_id`) for traded players,
so summing rows counts those players twice. Runs on `data_root()`: the real bundle
or the CI fixtures, whichever `TRACKLAB_DATA_ROOT` points at.
"""

from __future__ import annotations

import duckdb
import pytest

from tracklab.paths import data_root

BASKETBALL = ("aggregates_drives", "aggregates_picks", "aggregates_shots")
FOOTBALL = ("aggregates_obr", "aggregates_passing", "aggregates_physical")
KEYS = {
    "basketball": ("player_id", "team_id"),
    "football": ("player_id", "team_id", "position_group"),
}
TABLES = [("basketball", t) for t in BASKETBALL] + [("football", t) for t in FOOTBALL]

_missing = [
    f"{s}/{t}" for s, t in TABLES if not (data_root() / "bronze" / s / t / "data.parquet").is_file()
]
pytestmark = pytest.mark.skipif(
    bool(_missing), reason=f"no season aggregates under {data_root()}: {_missing}"
)


def _one(sport: str, table: str, sql: str) -> tuple[int, ...]:
    path = (data_root() / "bronze" / sport / table / "data.parquet").as_posix()
    row = duckdb.connect().execute(sql.format(t=f"read_parquet('{path}')")).fetchone()
    assert row is not None
    return tuple(int(v) for v in row)


@pytest.mark.parametrize(("sport", "table"), TABLES)
def test_the_measured_key_is_unique(sport: str, table: str) -> None:
    key = ", ".join(KEYS[sport])
    rows, players, teams, total = _one(
        sport,
        table,
        "SELECT count(*), count(DISTINCT player_id), count(DISTINCT team_id), "
        "count(*) FILTER (WHERE team_name = 'total') FROM {t}",
    )
    (distinct,) = _one(sport, table, f"SELECT count(*) FROM (SELECT DISTINCT {key} FROM {{t}})")
    print(
        f"\n{sport}/{table}: rows={rows} players={players} teams={teams} total_rows={total} "
        f"key=({key}) duplicated_rows={rows - distinct}"
    )
    assert rows == distinct, f"{table}: {rows - distinct} rows repeat the key ({key})"


@pytest.mark.parametrize("table", BASKETBALL)
def test_basketball_null_team_id_only_on_total_rows(table: str) -> None:
    null_not_total, total_not_null, total = _one(
        "basketball",
        table,
        "SELECT count(*) FILTER (WHERE team_id IS NULL AND team_name IS DISTINCT FROM 'total'), "
        "count(*) FILTER (WHERE team_name = 'total' AND team_id IS NOT NULL), "
        "count(*) FILTER (WHERE team_name = 'total') FROM {t}",
    )
    print(f"\nbasketball/{table}: total_rows={total}")
    assert (null_not_total, total_not_null) == (0, 0)
    assert total == 5


@pytest.mark.parametrize("table", FOOTBALL)
def test_football_has_no_total_rows(table: str) -> None:
    (total,) = _one(
        "football", table, "SELECT count(*) FILTER (WHERE team_name = 'total') FROM {t}"
    )
    print(f"\nfootball/{table}: total_rows={total}")
    assert total == 0
