"""`tracklab publish scouting` (task 134): pools, sample floors and percentiles on a toy Parquet.

Every expected number below is worked out by hand in the comments, never read back from the
producer. Football toy (floor 5 matches, pool per position_group, metric `speed`):

    group A: p1 6 matches speed 30 | p2 5 / 32 | p3 4 / 40 (below the floor) | p4 8 / 28
    group B: p5 9 / 35 | p6 5 / 31 | p7 2 / 33 (below the floor)

Basketball toy (floor 10 games, no total rows, one pool; metrics `pts / games_played`, `rate`):

    p1 20 games 40 pts rate .50 | p2 10 / 50 / .25 | p3 12 / 60 / null | p4 30 / 30 / .75
    p5 9 games (below the floor) | p6 a `total` row of 40 games, 2000 pts | p7 15 / 45 / .50
    points per game of the pool: p1 2, p2 5, p3 5, p4 1, p7 3
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest

from tracklab.paths import data_root
from tracklab.publish import scouting
from tracklab.publish.examples import MIN_GAMES, MIN_MATCHES
from tracklab.publish.scouting import (
    CATALOG,
    Metric,
    TableSpec,
    age_at,
    percentile,
    run_publish_scouting,
    table_block,
)

WEB_DATA = Path(__file__).resolve().parents[3] / "web" / "public" / "data"

FB = TableSpec(
    "fb_toy",
    "football",
    ("player_id", "team_id", "position_group"),
    "count_match",
    5,
    False,
    "position_group",
    (Metric("speed", "Speed", "km_per_h", "km/h"),),
)
BB = TableSpec(
    "bb_toy",
    "basketball",
    ("player_id", "team_id"),
    "games_played",
    10,
    True,
    None,
    (Metric("pts / games_played", "Points", "per_match"), Metric("rate", "Rate", "per_one")),
)

# (player_id, group, matches, speed, birthdate)
FB_ROWS = [
    (1, "A", 6, 30.0, date(2002, 6, 30)),
    (2, "A", 5, 32.0, date(2002, 7, 1)),
    (3, "A", 4, 40.0, None),
    (4, "A", 8, 28.0, date(1990, 1, 1)),
    (5, "B", 9, 35.0, date(2000, 1, 1)),
    (6, "B", 5, 31.0, date(2000, 1, 1)),
    (7, "B", 2, 33.0, date(2000, 1, 1)),
]
# (player_id, games, is_total, pts, rate)
BB_ROWS = [
    (1, 20, False, 40, 0.5),
    (2, 10, False, 50, 0.25),
    (3, 12, False, 60, None),
    (4, 30, False, 30, 0.75),
    (5, 9, False, 900, 0.99),
    (6, 40, True, 2000, 0.9),
    (7, 15, False, 45, 0.5),
]


def fb_rows() -> list[dict[str, Any]]:
    return [
        {
            "player_id": p,
            "team_id": 100,
            "position_group": g,
            "count_match": m,
            "speed": s,
            "player_name": f"P{p}",
            "team_name": "T",
            "player_birthdate": b,
        }
        for p, g, m, s, b in FB_ROWS
    ]


def bb_rows() -> list[dict[str, Any]]:
    return [
        {
            "player_id": p,
            "team_id": 200,
            "games_played": g,
            "is_season_total": t,
            "pts": pts,
            "rate": r,
            "player_name": f"P{p}",
            "team_name": "T",
        }
        for p, g, t, pts, r in BB_ROWS
    ]


def fb_probe(pid: int, group: str) -> tuple[Any, ...]:
    return (pid, 100, group)


def test_percentile_is_the_share_of_the_others_below_and_a_high_value_is_a_high_percentile() -> (
    None
):
    # [1, 2, 3, 4]: 4 has three below out of n - 1 = 3, 1 has none, a tie counts the ones below.
    assert percentile([1, 2, 3, 4], 4) == 100.0
    assert percentile([1, 2, 3, 4], 1) == 0.0
    assert percentile([1, 2, 2, 4], 2) == 33.3
    assert percentile([5], 5) == 0.0


def test_percentile_rounds_an_exact_tie_half_up() -> None:
    # n = 81: the second smallest has 1 below out of 80, 100 / 80 = 1.25 exactly; half up is 1.3
    # (DuckDB's round), half even would be 1.2. 3 below is 3.75, 3.8 either way.
    pool = list(range(81))
    assert percentile(pool, 1) == 1.3
    assert percentile(pool, 3) == 3.8


def test_age_is_completed_years_at_the_reference_date() -> None:
    assert age_at(date(2002, 6, 30)) == 23  # birthday on the reference day: already 23
    assert age_at(date(2002, 7, 1)) == 22  # the day after: still 22
    assert age_at(date(1990, 1, 1)) == 35
    assert age_at(None) is None


def test_football_pool_is_the_floor_inside_each_position_group() -> None:
    block = table_block(FB, fb_rows(), [fb_probe(1, "A"), fb_probe(6, "B")])
    pools = {p["group"]: p for p in block["pools"]}
    # A: p1, p2, p4 pass (p3 has 4 matches): 3 rows, 3 players, 6 + 5 + 8 = 19 matches.
    assert pools["A"]["rows"] == 3
    assert pools["A"]["players"] == 3
    assert pools["A"]["sample_total"] == 19
    # B: p5 and p6 pass (p7 has 2): 2 rows, 9 + 5 = 14 matches.
    assert (pools["B"]["rows"], pools["B"]["sample_total"]) == (2, 14)
    # Speeds of A are [30, 32, 28]: p1 has one below out of two = 50.0. Of B, [35, 31]: p6 is 0.0.
    assert block["probes"][0]["values"]["speed"] == [30.0, 50.0]
    assert block["probes"][1]["values"]["speed"] == [31.0, 0.0]


def test_a_probe_below_the_floor_has_no_values() -> None:
    (probe,) = table_block(FB, fb_rows(), [fb_probe(3, "A")])["probes"]
    assert probe["in_pool"] is False
    assert "values" not in probe


def test_the_lowered_floor_changes_the_pool_and_the_percentiles() -> None:
    block = table_block(replace(FB, floor=4), fb_rows(), [fb_probe(1, "A")])
    a = next(p for p in block["pools"] if p["group"] == "A")
    assert a["rows"] == 4  # p3 comes in
    # [30, 32, 40, 28]: p1 has one below out of three = 33.3, no longer 50.0.
    assert block["probes"][0]["values"]["speed"] == [30.0, 33.3]


def test_basketball_pool_leaves_out_total_rows_and_rows_below_the_floor() -> None:
    block = table_block(BB, bb_rows(), [(4, 200), (1, 200)])
    (pool,) = block["pools"]
    # p1 p2 p3 p4 p7 pass; p5 (9 games) and the `total` row of p6 do not.
    assert pool["group"] is None
    assert (pool["rows"], pool["players"]) == (5, 5)
    assert pool["sample_total"] == 20 + 10 + 12 + 30 + 15
    # points per game of the pool [2, 5, 5, 1, 3]: p4 (1.0) has none below, p1 (2.0) one of four.
    p4, p1 = block["probes"]
    assert p4["values"]["pts_per_game"] == [1.0, 0.0]
    assert p1["values"]["pts_per_game"] == [2.0, 25.0]


def test_a_null_sample_or_a_null_total_flag_does_not_pass_the_floor_as_in_the_sql() -> None:
    fb = {"count_match": None}
    assert FB.passes(fb) is False
    assert FB.passes({"count_match": 5}) is True
    assert BB.passes({"games_played": None, "is_season_total": False}) is False
    # NOT NULL is NULL in the WHERE: the row is out.
    assert BB.passes({"games_played": 20, "is_season_total": None}) is False
    assert BB.passes({"games_played": 20, "is_season_total": False}) is True
    assert BB.passes({"games_played": 20, "is_season_total": True}) is False


def test_the_default_pair_breaks_a_tie_in_the_sample_by_the_whole_key() -> None:
    rows = fb_rows()
    for r in rows:
        if r["position_group"] == "A":
            r["count_match"] = 7  # p1, p2, p4 all tied
    rows.append({**rows[0], "team_id": 101})  # player 1 again, in another team
    pair = scouting._default_pair([FB], {FB.table: rows})
    assert [(k[0], k[1]) for k in pair] == [(1, 100), (1, 101)]


def test_expression_per_game_divides_by_games_played() -> None:
    (p3,) = table_block(BB, bb_rows(), [(3, 200)])["probes"]
    assert p3["values"]["pts_per_game"] == [5.0, 75.0]  # 60 / 12; [2, 5, 5, 1, 3] has 3 below a 5


def test_nulls_leave_the_pool_and_have_no_percentile() -> None:
    block = table_block(BB, bb_rows(), [(3, 200), (1, 200), (4, 200)])
    (pool,) = block["pools"]
    # `rate` is null for p3: its pool has 4 values [.5, .25, .75, .5], `pts` has all 5.
    assert pool["n"] == [5, 4]
    p3, p1, p4 = block["probes"]
    assert p3["values"]["rate"] is None
    # Without the null in the pool, p1 (0.5) has one below out of three = 33.3 (with the null
    # ranked as a value it would be out of four) and p4 (0.75) is the top.
    assert p1["values"]["rate"] == [0.5, 33.3]
    assert p4["values"]["rate"] == [0.75, 100.0]


def test_a_metric_that_is_not_in_the_table_raises(tmp_path: Path) -> None:
    web, data = write_toy(tmp_path)
    broken = replace(FB, metrics=(Metric("no_such_column", "Nope", "per_match"),))
    with pytest.raises(ValueError, match="no_such_column"):
        scouting.build(web, data, (broken,))


def write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    con = duckdb.connect()
    columns = list(rows[0])
    con.execute(
        "CREATE TABLE t AS SELECT * FROM (VALUES "
        + ", ".join("(" + ", ".join(_sql(r[c]) for c in columns) + ")" for r in rows)
        + ") v("
        + ", ".join(columns)
        + ")"
    )
    con.execute(f"COPY t TO '{path.as_posix()}' (FORMAT PARQUET)")


def _sql(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return f"DATE '{value.isoformat()}'"
    if isinstance(value, str):
        return f"'{value}'"
    return repr(value)


def write_toy(root: Path) -> tuple[Path, Path]:
    web = root / "web"
    (web / "warehouse").mkdir(parents=True)
    write_parquet(web / "warehouse" / "fb_toy.aaaa.parquet", fb_rows())
    write_parquet(web / "warehouse" / "bb_toy.bbbb.parquet", bb_rows())
    (web / "warehouse.json").write_text(
        json.dumps(
            {
                "tables": [
                    {"table": "fb_toy", "file": "fb_toy.aaaa.parquet"},
                    {"table": "bb_toy", "file": "bb_toy.bbbb.parquet"},
                ]
            }
        ),
        encoding="utf-8",
    )
    aliases = root / "data" / "bronze" / "basketball" / "player_id_aliases"
    aliases.mkdir(parents=True)
    write_parquet(
        aliases / "data.parquet",
        [
            {"player_id": 2, "canonical_player_id": 1},
            {"player_id": 1, "canonical_player_id": 1},
        ],
    )
    return web, root / "data"


def test_the_published_file_names_the_parquet_it_read_and_carries_no_birthdate(
    tmp_path: Path,
) -> None:
    web, data = write_toy(tmp_path)
    payload = scouting.build(web, data, (FB, BB))
    text = scouting.render(payload)
    assert "birth" not in text and "2002" not in text and "1990" not in text
    assert "\r" not in text
    fb, bb = payload["tables"]
    assert len(fb["sha256"]) == 64 and fb["file"] == "fb_toy.aaaa.parquet"
    assert fb["floor"] == "count_match >= 5"
    assert bb["floor"] == "NOT is_season_total AND games_played >= 10"
    # Every row of the Parquet, so the page can say how many are under the floor: the pools hold
    # 5 of football's 7 (p3 has 4 matches, p7 has 2) and 5 of basketball's 7 (p5, the total of p6).
    assert (fb["rows_total"], bb["rows_total"]) == (7, 7)
    assert sum(p["rows"] for p in fb["pools"]) == 5 and sum(p["rows"] for p in bb["pools"]) == 5
    assert payload["aliases"] == [{"player_id": 2, "canonical_player_id": 1}]
    # Default pair of football: the group with most players is A; the most matches are p4 (8)
    # then p1 (6); p4 was born in 1990 (35), p1 on the reference day in 2002 (23).
    pair = payload["default_pairs"]["football"]
    assert [(p["player_id"], p["age"]) for p in pair] == [(4, 35), (1, 23)]
    # Basketball: the most games in the pool are p4 (30) then p1 (20).
    assert [p["player_id"] for p in payload["default_pairs"]["basketball"]] == [4, 1]


def test_check_fails_when_a_parquet_is_republished(tmp_path: Path) -> None:
    web, data = write_toy(tmp_path)
    payload = scouting.build(web, data, (FB, BB))
    (web / scouting.SCOUTING_JSON).write_text(scouting.render(payload), encoding="utf-8")
    again = scouting.build(web, data, (FB, BB))
    assert scouting.render(again) == (web / scouting.SCOUTING_JSON).read_text(encoding="utf-8")
    # Same rows, other bytes: the sha256 moves and the committed file is stale.
    rows = fb_rows()
    rows[0]["speed"] = 30.5
    write_parquet(web / "warehouse" / "fb_toy.aaaa.parquet", rows)
    changed = scouting.render(scouting.build(web, data, (FB, BB)))
    assert changed != (web / scouting.SCOUTING_JSON).read_text(encoding="utf-8")


def test_the_real_catalog_floors_are_the_params_of_the_examples_file() -> None:
    params = json.loads((WEB_DATA / "warehouse_examples.json").read_text(encoding="utf-8"))[
        "params"
    ]
    assert (MIN_MATCHES, MIN_GAMES) == (params["min_matches"], params["min_games"])
    floors = {s.table: s.floor for s in CATALOG}
    assert floors == {
        "fb_physical": params["min_matches"],
        "fb_passing": params["min_matches"],
        "fb_obr": params["min_matches"],
        "bb_shots": params["min_games"],
        "bb_drives": params["min_games"],
        "bb_picks": params["min_games"],
    }
    assert sum(len(s.metrics) for s in CATALOG) == 61


built = pytest.mark.skipif(
    not (
        (WEB_DATA / "scouting.json").is_file()
        and (data_root() / "bronze" / "basketball" / "player_id_aliases").is_dir()
    ),
    reason="needs the published files and the bronze aliases",
)


@built
def test_the_committed_scouting_file_is_what_the_published_parquet_give() -> None:
    assert run_publish_scouting(data_root(), WEB_DATA, check=True) == 0


@built
def test_check_fails_when_the_file_is_not_what_the_parquet_give(tmp_path: Path) -> None:
    (tmp_path / "warehouse.json").write_bytes((WEB_DATA / "warehouse.json").read_bytes())
    shutil.copytree(WEB_DATA / "warehouse", tmp_path / "warehouse")
    (tmp_path / scouting.SCOUTING_JSON).write_text("{}\n", encoding="utf-8")
    assert run_publish_scouting(data_root(), tmp_path, check=True) == 1
