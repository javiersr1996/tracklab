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

    football = con.execute(
        f"""WITH pool AS (
              SELECT * FROM read_parquet('{physical}')
              WHERE {examples.FOOTBALL_METRIC} IS NOT NULL AND count_match >= {examples.MIN_MATCHES})
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
    assert figures["pool_rows_merged"] == (
        figures["pool_rows_naive"] - figures["people_in_pool_twice"] + figures["rows_added_by_folding"]
    )
