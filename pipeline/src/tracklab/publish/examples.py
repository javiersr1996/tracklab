"""`tracklab publish examples`: what the example queries of `/warehouse` must return, and how much
the basketball alias ids move them (task 43, P4).

`web/public/data/warehouse_examples.json` is computed here from gold with plain Python (sorting
and counting), not with the SQL the page runs in the browser: the e2e compares the engine's
answer with it, so it has to come from another path. The same file carries the alias figures
the page quotes. `--check` regenerates in memory and compares the file byte for byte.

Aliases: `player_id_aliases` maps provider ids that changed to a canonical id. Gold keeps the
provider id (rewriting would break the grain), so a person whose old and new ids sit in the same
team is two rows. `merged` below folds the alias row into its canonical row (summing the counts)
to say how much a query changes.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb

EXAMPLES_JSON = "warehouse_examples.json"

# The people the example queries look at; the SQL in `web/lib/warehouse/examples.ts`
# names the same ones. Each name is checked to be unique in its table.
PROFILE_PLAYER = "Timothe Luwawu-Cabarrot"
FOOTBALL_PLAYER = "Jay Barnett"
BASKETBALL_PLAYER = "Guillem Vives"
MIN_MATCHES = 5
MIN_GAMES = 10
FOOTBALL_METRIC = "psv99"


def percent_rank(values: list[float], value: float) -> float:
    """Share of the other values below `value`: (rank - 1) / (n - 1), as SQL `percent_rank()`."""
    return sum(1 for v in values if v < value) / (len(values) - 1)


def quantile(values: list[float], q: float) -> float:
    """Linear interpolation between the closest ranks, as SQL `quantile_cont`."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _rows(con: duckdb.DuckDBPyConnection, gold: Path, model: str) -> list[dict[str, Any]]:
    cursor = con.execute(
        f"SELECT * FROM read_parquet('{(gold / model / 'data.parquet').as_posix()}')"
    )
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _only(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    found = [r for r in rows if r["player_name"] == name]
    if len(found) != 1:
        raise ValueError(f"{name!r}: {len(found)} rows, expected exactly one")
    return found[0]


def _example(
    example_id: str, table: str, columns: list[tuple[str, int | None]], rows: list[list[Any]]
) -> dict[str, Any]:
    return {
        "id": example_id,
        "table": table,
        "columns": [{"name": n, "decimals": d} for n, d in columns],
        "rows": rows,
    }


def _shooting_pool(
    shots: list[dict[str, Any]], merge: dict[int, int] | None
) -> list[dict[str, Any]]:
    """Team rows of bb_shots with `games_played >= MIN_GAMES`, optionally with alias ids folded
    into their canonical id (same team), summing games and three-point attempts."""
    folded: dict[tuple[int, int], dict[str, Any]] = {}
    for r in shots:
        if r["is_season_total"]:
            continue
        pid = (merge or {}).get(r["player_id"], r["player_id"])
        key = (pid, r["team_id"])
        row = folded.setdefault(
            key,
            {
                "player_id": pid,
                "team_id": r["team_id"],
                "player_name": r["player_name"],
                "team_name": r["team_name"],
                "games": 0,
                "threes": 0,
            },
        )
        if r["player_id"] == pid:
            row["player_name"] = r["player_name"]
        row["games"] += r["games_played"]
        row["threes"] += r["three_attempts"]
    return [r for r in folded.values() if r["games"] >= MIN_GAMES]


def build(data_dir: Path) -> dict[str, Any]:
    con = duckdb.connect()
    gold = data_dir / "gold"
    shots = _rows(con, gold, "agg_bb_shots")
    physical = _rows(con, gold, "agg_fb_physical")
    fact = _rows(con, gold, "fact_player_season_metric")
    alias_files = (data_dir / "bronze" / "basketball" / "player_id_aliases").glob("*.parquet")
    alias_rows = [
        r
        for f in sorted(alias_files)
        for r in con.execute(
            f"SELECT player_id, canonical_player_id FROM read_parquet('{f.as_posix()}')"
        ).fetchall()
    ]
    merge = {a: c for a, c in alias_rows if a != c}

    # 1. Profile: one player's season line.
    p = _only([r for r in shots if not r["is_season_total"]], PROFILE_PLAYER)
    profile = _example(
        "profile",
        "bb_shots",
        [
            ("player_name", None),
            ("team_name", None),
            ("games_played", None),
            ("attempts", None),
            ("mades", None),
            ("three_attempts", None),
            ("three_mades", None),
            ("total_points", None),
            ("points_per_game", 1),
        ],
        [
            [
                p["player_name"],
                p["team_name"],
                p["games_played"],
                p["attempts"],
                p["mades"],
                p["three_attempts"],
                p["three_mades"],
                p["total_points"],
                p["total_points"] / p["games_played"],
            ]
        ],
    )

    # 2. Percentile of top speed inside the player's position, with its pool: the players in it
    # and the matches they played between them (a sum over players: one match counts once per
    # player who played it, so it is not a count of matches).
    pool = [
        r for r in physical if r[FOOTBALL_METRIC] is not None and r["count_match"] >= MIN_MATCHES
    ]
    me = _only(pool, FOOTBALL_PLAYER)
    group = [r for r in pool if r["position_group"] == me["position_group"]]
    percentile = _example(
        "percentile",
        "fb_physical",
        [
            ("player_name", None),
            ("team_name", None),
            ("position_group", None),
            (FOOTBALL_METRIC, 2),
            ("percentile", 1),
            ("players_in_group", None),
            ("player_matches_in_group", None),
        ],
        [
            [
                me["player_name"],
                me["team_name"],
                me["position_group"],
                me[FOOTBALL_METRIC],
                100 * percent_rank([r[FOOTBALL_METRIC] for r in group], me[FOOTBALL_METRIC]),
                len({r["player_id"] for r in group}),
                sum(r["count_match"] for r in group),
            ]
        ],
    )

    # 3. Teams side by side: sums of counts over the team rows, never the `total` rows.
    teams: dict[str, dict[str, int]] = defaultdict(lambda: {"attempts": 0, "mades": 0, "points": 0})
    for r in shots:
        if not r["is_season_total"]:
            t = teams[r["team_name"]]
            t["attempts"] += r["attempts"]
            t["mades"] += r["mades"]
            t["points"] += r["total_points"]
    ranked = sorted(teams.items(), key=lambda kv: (-kv[1]["points"], kv[0]))
    team_example = _example(
        "teams",
        "bb_shots",
        [("team_name", None), ("attempts", None), ("mades", None), ("fg_pct", 1), ("points", None)],
        [
            [name, t["attempts"], t["mades"], 100 * t["mades"] / t["attempts"], t["points"]]
            for name, t in ranked
        ],
    )

    # 4. The long fact for one metric: the quantiles over its rows (row groups are sorted by it).
    values = [
        r["value"]
        for r in fact
        if r["metric"] == FOOTBALL_METRIC
        and r["sport"] == "football"
        and r["family"] == "physical"
        and not r["is_season_total"]
    ]
    fact_example = _example(
        "fact",
        "fact",
        [("p50", 2), ("p90", 2), ("n", None)],
        [[quantile(values, 0.5), quantile(values, 0.9), len(values)]],
    )

    # 5. Percentile of three-point attempts per game among basketball players with enough games,
    # with the player ids in the pool and the games they played between them (a sum, as above).
    def shooting(pool_rows: list[dict[str, Any]]) -> dict[str, Any]:
        rates = [r["threes"] / r["games"] for r in pool_rows]
        mine = [r for r in pool_rows if r["player_name"] == BASKETBALL_PLAYER]
        if len(mine) != 1:
            raise ValueError(f"{BASKETBALL_PLAYER!r}: {len(mine)} rows in the pool")
        r = mine[0]
        return {
            "row": [
                r["player_name"],
                r["team_name"],
                r["games"],
                r["threes"],
                r["threes"] / r["games"],
                100 * percent_rank(rates, r["threes"] / r["games"]),
                len({x["player_id"] for x in pool_rows}),
                sum(x["games"] for x in pool_rows),
            ],
            "pool_rows": len(pool_rows),
            "percentile": 100 * percent_rank(rates, r["threes"] / r["games"]),
        }

    naive_pool = _shooting_pool(shots, None)
    merged_pool = _shooting_pool(shots, merge)
    naive = shooting(naive_pool)
    merged = shooting(merged_pool)
    # The pool as people: an alias row and its canonical row on the same team are one person
    # counted twice. Folding them sums their games, which can also lift into the pool a person
    # whose two ids each had fewer than MIN_GAMES (rows the naive pool does not have at all).
    naive_people = {(merge.get(r["player_id"], r["player_id"]), r["team_id"]) for r in naive_pool}
    merged_keys = {(r["player_id"], r["team_id"]) for r in merged_pool}
    basketball = _example(
        "basketball_percentile",
        "bb_shots",
        [
            ("player_name", None),
            ("team_name", None),
            ("games_played", None),
            ("three_attempts", None),
            ("threes_per_game", 2),
            ("percentile", 1),
            ("player_ids_in_pool", None),
            ("player_games_in_pool", None),
        ],
        [naive["row"]],
    )

    # Alias ids in bb_shots that share a team with their canonical id, and what the one query
    # that ranks basketball players moves. Football has no alias file; the team sums do not
    # depend on `player_id`.
    in_team = {(r["player_id"], r["team_id"]) for r in shots if not r["is_season_total"]}
    shared = sorted(
        a
        for a, c in merge.items()
        if any((a, t) in in_team and (c, t) in in_team for _, t in in_team)
    )
    in_aliases = {i for pair in merge.items() for i in pair}
    aliases = {
        "alias_ids": len(merge),
        "bb_shots_alias_rows_in_a_team_with_their_canonical_id": len(shared),
        "profile_player_has_an_alias": p["player_id"] in in_aliases,
        "basketball_percentile": {
            "pool_rows_naive": naive["pool_rows"],
            "pool_rows_merged": merged["pool_rows"],
            "people_in_pool_twice": len(naive_pool) - len(naive_people),
            "rows_added_by_folding": len(merged_keys - naive_people),
            "percentile_naive": naive["percentile"],
            "percentile_merged": merged["percentile"],
        },
    }
    return {
        "schema_version": 1,
        "params": {
            "min_matches": MIN_MATCHES,
            "min_games": MIN_GAMES,
            "football_metric": FOOTBALL_METRIC,
            "profile_player": PROFILE_PLAYER,
            "football_player": FOOTBALL_PLAYER,
            "basketball_player": BASKETBALL_PLAYER,
        },
        "examples": [profile, percentile, team_example, fact_example, basketball],
        "aliases": aliases,
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def run_publish_examples(data_dir: Path, out_dir: Path, *, check: bool = False) -> int:
    try:
        text = render(build(data_dir))
    except (FileNotFoundError, duckdb.IOException, ValueError) as error:
        print(f"publish examples: {error}")
        return 1
    path = out_dir / EXAMPLES_JSON
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            print(f"publish examples --check: {EXAMPLES_JSON} differs from what gold produces")
            return 1
        print(f"publish examples --check: {EXAMPLES_JSON} matches gold")
        return 0
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"publish examples: {path} ({path.stat().st_size} bytes)")
    return 0
