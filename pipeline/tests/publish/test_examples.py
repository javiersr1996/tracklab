"""`tracklab publish examples` (task 43): the expected answers of the `/warehouse` example
queries are computed in Python, so the e2e compares the browser engine with another path."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tracklab.paths import data_root
from tracklab.publish import examples
from tracklab.publish.examples import percent_rank, quantile, run_publish_examples

WEB_DATA = Path(__file__).resolve().parents[3] / "web" / "public" / "data"

built = pytest.mark.skipif(
    not (
        (data_root() / "gold" / "agg_bb_shots" / "data.parquet").is_file()
        and (data_root() / "bronze" / "basketball" / "player_id_aliases").is_dir()
    ),
    reason="needs gold and the bronze aliases",
)


def test_percent_rank_counts_the_values_below_over_the_others() -> None:
    assert percent_rank([1, 2, 3, 4], 4) == 1.0
    assert percent_rank([1, 2, 3, 4], 1) == 0.0
    assert percent_rank([1, 2, 2, 4], 2) == pytest.approx(1 / 3)


def test_quantile_interpolates_between_ranks() -> None:
    assert quantile([4, 1, 3, 2], 0.5) == 2.5
    assert quantile([1, 2, 3, 4, 5], 0.9) == pytest.approx(4.6)
    assert quantile([7], 0.9) == 7


@built
def test_the_committed_examples_are_what_gold_gives() -> None:
    assert run_publish_examples(data_root(), WEB_DATA, check=True) == 0


@built
def test_check_fails_when_the_file_is_not_what_gold_gives(tmp_path: Path) -> None:
    (tmp_path / examples.EXAMPLES_JSON).write_text("{}\n", encoding="utf-8")
    assert run_publish_examples(data_root(), tmp_path, check=True) == 1


@built
def test_every_example_is_one_player_or_the_lists_it_says() -> None:
    payload = examples.build(data_root())
    by_id = {e["id"]: e for e in payload["examples"]}
    assert len(by_id["profile"]["rows"]) == 1
    assert len(by_id["fact"]["rows"]) == 1
    # Basketball team rows only: the `total` rows of traded players are not a team.
    assert "total" not in {r[0] for r in by_id["teams"]["rows"]}
    assert payload["aliases"]["profile_player_has_an_alias"] is False


@built
def test_the_percentile_denominators_count_what_their_names_say() -> None:
    """Review of 38, 42 and 43 (M2): the pools printed `matches_in_group` and `games_in_pool`,
    which are sums over the players (a match counts once per player in it), and the basketball
    pool counts a person twice when an old and a new id of his are both in it. Recounted here with
    SQL over gold and the alias file, another path than the loops of `build`."""
    payload = examples.build(data_root())
    row = {
        e["id"]: dict(zip([c["name"] for c in e["columns"]], e["rows"][0], strict=True))
        for e in payload["examples"]
    }
    gold = data_root() / "gold"
    physical = (gold / "agg_fb_physical" / "data.parquet").as_posix()
    shots = (gold / "agg_bb_shots" / "data.parquet").as_posix()
    aliases = (data_root() / "bronze" / "basketball" / "player_id_aliases" / "*.parquet").as_posix()
    con = duckdb.connect()

    metric, min_matches = examples.FOOTBALL_METRIC, examples.MIN_MATCHES
    football = con.execute(
        f"""WITH pool AS (
              SELECT * FROM read_parquet('{physical}')
              WHERE {metric} IS NOT NULL AND count_match >= {min_matches})
            SELECT count(DISTINCT player_id), sum(count_match) FROM pool
            WHERE position_group = (SELECT position_group FROM pool WHERE player_name = ?)""",
        [examples.FOOTBALL_PLAYER],
    ).fetchone()
    percentile = row["percentile"]
    assert (percentile["players_in_group"], percentile["player_matches_in_group"]) == football

    pool = f"""SELECT player_id, team_id, games_played FROM read_parquet('{shots}')
               WHERE NOT is_season_total AND games_played >= {examples.MIN_GAMES}"""
    basketball = con.execute(
        f"SELECT count(DISTINCT player_id), sum(games_played) FROM ({pool})"
    ).fetchone()
    shooting = row["basketball_percentile"]
    assert (shooting["player_ids_in_pool"], shooting["player_games_in_pool"]) == basketball

    # People in the pool under two ids: an alias and its canonical id, same team, both in it.
    twice = con.execute(
        f"""WITH pool AS ({pool}),
                 alias AS (SELECT player_id AS a, canonical_player_id AS c
                           FROM read_parquet('{aliases}') WHERE player_id <> canonical_player_id)
            SELECT count(*) FROM alias
            JOIN pool old ON old.player_id = alias.a
            JOIN pool new ON new.player_id = alias.c AND new.team_id = old.team_id"""
    ).fetchone()
    figures = payload["aliases"]["basketball_percentile"]
    assert twice is not None
    assert figures["people_in_pool_twice"] == twice[0]
    folded = figures["pool_rows_naive"] - twice[0] + figures["rows_added_by_folding"]
    assert figures["pool_rows_merged"] == folded


def _write(con: duckdb.DuckDBPyConnection, path: Path, query: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({query}) TO '{path.as_posix()}' (FORMAT parquet)")


def test_the_denominators_count_people_not_rows_when_a_player_has_two_team_rows(
    tmp_path: Path,
) -> None:
    """Second pass on 38, 42 and 43 (N3): on today's gold rows and ids coincide, so `len(rows)`
    in place of the distinct ids passed every test. Here a traded player has a row per team (same
    id), in the football group and in the basketball pool: 4 rows, 3 people."""
    gold = tmp_path / "gold"
    con = duckdb.connect()
    _write(
        con,
        gold / "agg_bb_shots" / "data.parquet",
        f"""SELECT * FROM (VALUES
              (1, 10, 'Timothe Luwawu-Cabarrot', 'A', FALSE, 20, 40, 100, 50, 20, 120),
              (2, 10, '{examples.BASKETBALL_PLAYER}', 'A', FALSE, 20, 40, 100, 50, 20, 120),
              (3, 10, 'Traded', 'A', FALSE, 15, 10, 50, 20, 4, 50),
              (3, 11, 'Traded', 'B', FALSE, 12, 6, 30, 10, 2, 30)
            ) t(player_id, team_id, player_name, team_name, is_season_total, games_played,
                three_attempts, attempts, mades, three_mades, total_points)""",
    )
    _write(
        con,
        gold / "agg_fb_physical" / "data.parquet",
        f"""SELECT * FROM (VALUES
              (1, '{examples.FOOTBALL_PLAYER}', 'A', 'G', 30.0::DOUBLE, 10),
              (2, 'Other', 'A', 'G', 28.0::DOUBLE, 6),
              (2, 'Other', 'B', 'G', 29.0::DOUBLE, 7)
            ) t(player_id, player_name, team_name, position_group, {examples.FOOTBALL_METRIC},
                count_match)""",
    )
    _write(
        con,
        gold / "fact_player_season_metric" / "data.parquet",
        f"""SELECT * FROM (VALUES
              ('football', 'physical', '{examples.FOOTBALL_METRIC}', FALSE, 30.0::DOUBLE))
            t(sport, family, metric, is_season_total, value)""",
    )
    _write(
        con,
        tmp_path / "bronze" / "basketball" / "player_id_aliases" / "a.parquet",
        "SELECT 7 AS player_id, 8 AS canonical_player_id",
    )

    payload = examples.build(tmp_path)
    row = {
        e["id"]: dict(zip([c["name"] for c in e["columns"]], e["rows"][0], strict=True))
        for e in payload["examples"]
    }
    assert row["percentile"]["players_in_group"] == 2  # 3 rows
    assert row["percentile"]["player_matches_in_group"] == 23
    assert row["basketball_percentile"]["player_ids_in_pool"] == 3  # 4 rows
    assert row["basketball_percentile"]["player_games_in_pool"] == 67
