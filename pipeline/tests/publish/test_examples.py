"""`tracklab publish examples` (task 43): the expected answers of the `/warehouse` example
queries are computed in Python, so the e2e compares the browser engine with another path."""

from __future__ import annotations

from pathlib import Path

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
