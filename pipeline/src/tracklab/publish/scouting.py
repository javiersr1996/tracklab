"""`tracklab publish scouting`: what the scouting page of `/warehouse` must show (task 134, P17).

`web/public/data/scouting.json` is computed here with plain Python (comparing and counting), from
the Parquet files the visitor reads (`web/public/data/warehouse/`, found through `warehouse.json`),
not from gold and not with the SQL the page runs in the browser: the e2e compares the engine's
answer with it, so it has to come from another path. Each Parquet's sha256 is inside, so a
republished warehouse fails `--check` until this file is regenerated.

The pool of a metric is the rows that pass the sample floor of their table, inside their
`position_group` in football (the league as a whole in basketball), whose value is not null. The
percentile is `percent_rank` (rank - 1) / (n - 1) over that pool, ascending, times 100, rounded to
one decimal with ROUND_HALF_UP (what DuckDB's `round` does on an exact tie; Python's `round` does
not). A high percentile is a high value, not a verdict. A null value has no percentile and leaves
the pool of its metric.

Age (football) is the Parquet's `player_age`, completed years at `AGE_REFERENCE` (the warehouse publisher's); no date of birth is published.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import duckdb

from tracklab.publish.examples import MIN_GAMES, MIN_MATCHES
from tracklab.publish.warehouse import AGE, AGE_REFERENCE

SCOUTING_JSON = "scouting.json"
SCHEMA_VERSION = 1
PER_GAME = " / games_played"

# Scales: per_one (a share, 0 to 1), per_hundred (0 to 100), per_match, per_action,
# per_30_tip (per 30 minutes in possession), m_per_min, km_per_h.


@dataclass(frozen=True)
class Metric:
    expr: str  # a column, or `column / games_played`
    label: str
    scale: str
    unit: str = ""

    @property
    def column(self) -> str:
        return self.expr.removesuffix(PER_GAME)

    @property
    def id(self) -> str:
        return self.column + ("_per_game" if self.expr.endswith(PER_GAME) else "")


@dataclass(frozen=True)
class TableSpec:
    table: str
    sport: str
    key: tuple[str, ...]
    sample: str  # the column the floor counts: matches, performances or games
    floor: int
    drop_season_total: bool
    partition: str | None
    metrics: tuple[Metric, ...]

    @property
    def floor_text(self) -> str:
        text = f"{self.sample} >= {self.floor}"
        return f"NOT is_season_total AND {text}" if self.drop_season_total else text

    def passes(self, row: dict[str, Any]) -> bool:
        # As the SQL's WHERE: a NULL sample or a NULL is_season_total is not a row that passes.
        if self.drop_season_total and row["is_season_total"] is not False:
            return False
        sample = row[self.sample]
        return sample is not None and bool(sample >= self.floor)


FB_KEY = ("player_id", "team_id", "position_group")
BB_KEY = ("player_id", "team_id")
P30 = "per_30_tip"


def _p30(column: str, label: str) -> Metric:
    return Metric(column, label, P30)


def _by_game(column: str, label: str) -> Metric:
    return Metric(column + PER_GAME, label, "per_match")


def _one(column: str, label: str) -> Metric:
    return Metric(column, label, "per_one")


def _action(column: str, label: str, unit: str = "") -> Metric:
    return Metric(column, label, "per_action", unit)


CATALOG: tuple[TableSpec, ...] = (
    TableSpec(
        "fb_physical",
        "football",
        FB_KEY,
        "count_match",
        MIN_MATCHES,
        False,
        "position_group",
        (
            Metric("total_distance_full_all", "Distance", "per_match", "m"),
            Metric("total_metersperminute_full_all", "Distance per min", "m_per_min", "m/min"),
            Metric("hsr_distance_full_all", "HSR distance", "per_match", "m"),
            Metric("hsr_count_full_all", "HSR runs", "per_match"),
            Metric("sprint_distance_full_all", "Sprint distance", "per_match", "m"),
            Metric("sprint_count_full_all", "Sprints", "per_match"),
            Metric("psv99", "Peak speed", "km_per_h", "km/h"),
            Metric("medaccel_count_full_all", "Medium accels", "per_match"),
            Metric("highaccel_count_full_all", "High accels", "per_match"),
            Metric("highdecel_count_full_all", "High decels", "per_match"),
        ),
    ),
    TableSpec(
        "fb_passing",
        "football",
        FB_KEY,
        "performance_count",
        MIN_MATCHES,
        False,
        "position_group",
        (
            _p30("pass_count_attempted_p30tip", "Passes"),
            _p30("pass_count_completed_p30tip", "Completed"),
            _p30("pass_count_linebreak_attempted_p30tip", "Line-breaks"),
            _p30("pass_count_dangerous_attempted_p30tip", "Dangerous"),
            _p30("pass_count_longrange_attempted_p30tip", "Long-range"),
            _p30("pass_count_torun_attempted_p30tip", "To a run"),
            _p30("pass_count_difficultpass_attempted_p30tip", "Difficult"),
            Metric("pass_pct_completed", "Completion", "per_hundred"),
            Metric("pass_avgxpass_attempted", "xPass", "per_hundred"),
            _action("pass_avgdistance", "Pass length", "m"),
        ),
    ),
    TableSpec(
        "fb_obr",
        "football",
        FB_KEY,
        "performance_count",
        MIN_MATCHES,
        False,
        "position_group",
        (
            _p30("offballrun_count_p30tip", "Off-ball runs"),
            _p30("behindrun_count_p30tip", "Behind"),
            _p30("overlaprun_count_p30tip", "Overlap"),
            _p30("underlaprun_count_p30tip", "Underlap"),
            _p30("supportrun_count_p30tip", "Support"),
            _p30("droppingoffrun_count_p30tip", "Dropping off"),
            _p30("aheadoftheballrun_count_p30tip", "Ahead of ball"),
            _p30("offballrun_count_dangerous_p30tip", "Dangerous runs"),
            _p30("offballrun_count_received_p30tip", "Runs received"),
            _action("offballrun_avgdistance", "Run length", "m"),
        ),
    ),
    TableSpec(
        "bb_shots",
        "basketball",
        BB_KEY,
        "games_played",
        MIN_GAMES,
        True,
        None,
        (
            _one("fg_percentage", "FG%"),
            _one("two_pt_percentage", "2P%"),
            _one("three_pt_percentage", "3P%"),
            _one("ft_percentage", "FT%"),
            _one("efg_percentage", "eFG%"),
            _one("three_pa_rate", "3PA rate"),
            _one("rim_attempt_rate", "Rim rate"),
            _one("rim_fg_percentage", "Rim FG%"),
            _action("points_per_shot", "Points per shot"),
            _action("avg_attempts_distance", "Shot distance", "m"),
            _by_game("total_points", "Points"),
        ),
    ),
    TableSpec(
        "bb_drives",
        "basketball",
        BB_KEY,
        "games_played",
        MIN_GAMES,
        True,
        None,
        (
            _by_game("total_drives", "Drives"),
            _action("points_per_drive", "Points per drive"),
            _action("points_per_shot_in_drive", "Points per shot in drive"),
            _one("successful_drives_rate", "Successful"),
            _one("made_baskets_rate", "Made baskets"),
            _one("assists_rate", "Assists"),
            _one("potential_assists_rate", "Potential assists"),
            _one("fouls_rate", "Fouls"),
            _one("end_type_turnover_rate", "Turnovers"),
            _one("end_type_kickout_rate", "Kick-outs"),
        ),
    ),
    TableSpec(
        "bb_picks",
        "basketball",
        BB_KEY,
        "games_played",
        MIN_GAMES,
        True,
        None,
        (
            _by_game("handler_total_picks", "Picks as handler"),
            _by_game("screener_total_picks", "Picks as screener"),
            _action("handler_ppp", "Handler points per pick"),
            _action("screener_ppp", "Screener points per pick"),
            _one("handler_score_rate", "Handler scores"),
            _one("handler_turnover_rate", "Handler turnovers"),
            _one("handler_assist_rate", "Handler assists"),
            _one("screener_score_rate", "Screener scores"),
            _one("screener_turnover_rate", "Screener turnovers"),
            _one("screener_success_rate", "Screener success"),
        ),
    ),
)

SPORTS = ("football", "basketball")


def percentile(pool: Sequence[float], value: float) -> float:
    """`percent_rank` of `value` among `pool` times 100, one decimal, ties rounded half up.

    Integer counting and Decimal arithmetic: 231 of 240 gives exactly 96.25, which rounds to 96.3
    as DuckDB's `round` does (a float `100 * 231 / 240` could land either side of the tie).
    """
    if len(pool) < 2:
        return 0.0
    below = sum(1 for v in pool if v < value)
    exact = Decimal(below * 100) / Decimal(len(pool) - 1)
    return float(exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _round_value(value: float) -> float:
    return float(Decimal(repr(float(value))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _value(row: dict[str, Any], metric: Metric) -> float | None:
    raw = row[metric.column]
    if raw is None:
        return None
    return float(raw / row["games_played"]) if metric.expr.endswith(PER_GAME) else float(raw)


def _key(spec: TableSpec, row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row[k] for k in spec.key)


def _group(spec: TableSpec, row: dict[str, Any]) -> str | None:
    return row[spec.partition] if spec.partition else None


def _needed(spec: TableSpec) -> set[str]:
    cols = {*spec.key, spec.sample, "player_name", "team_name"}
    cols |= {m.column for m in spec.metrics}
    if spec.drop_season_total:
        cols |= {"is_season_total", "games_played"}
    if spec.sport == "football":
        cols.add(AGE)
    return cols


def _check_columns(spec: TableSpec, names: set[str]) -> None:
    missing = sorted(_needed(spec) - names)
    if missing:
        raise ValueError(f"{spec.table}: no such column(s) in the Parquet: {', '.join(missing)}")
    for m in spec.metrics:
        if m.expr.endswith(PER_GAME) and "games_played" not in names:
            raise ValueError(f"{spec.table}: {m.expr!r} needs games_played")


def table_block(
    spec: TableSpec, rows: list[dict[str, Any]], probes: list[tuple[Any, ...]]
) -> dict[str, Any]:
    """The pools and the probe values of one table. `probes` are keys (`spec.key` order)."""
    pool_rows = [r for r in rows if spec.passes(r)]
    groups = sorted({_group(spec, r) for r in pool_rows}, key=lambda g: (g is None, g or ""))
    pool_values: dict[tuple[str | None, str], list[float]] = {}
    pools = []
    for g in groups:
        members = [r for r in pool_rows if _group(spec, r) == g]
        counts = []
        for m in spec.metrics:
            vals = [v for r in members if (v := _value(r, m)) is not None]
            pool_values[(g, m.id)] = vals
            counts.append(len(vals))
        pools.append(
            {
                "group": g,
                "rows": len(members),
                "players": len({r["player_id"] for r in members}),
                "sample_total": sum(r[spec.sample] for r in members),
                "n": counts,
            }
        )
    by_key = {_key(spec, r): r for r in rows}
    probe_blocks = []
    for key in probes:
        row = by_key[key]
        block: dict[str, Any] = dict(zip(spec.key, key, strict=True))
        block["in_pool"] = spec.passes(row)
        if block["in_pool"]:
            values = {}
            for m in spec.metrics:
                v = _value(row, m)
                values[m.id] = (
                    None
                    if v is None
                    else [_round_value(v), percentile(pool_values[(_group(spec, row), m.id)], v)]
                )
            block["values"] = values
        probe_blocks.append(block)
    return {"pools": pools, "probes": probe_blocks}


def _read(
    con: duckdb.DuckDBPyConnection, spec: TableSpec, path: Path
) -> tuple[list[dict[str, Any]], bytes]:
    data = path.read_bytes()
    cursor = con.execute(f"SELECT * FROM read_parquet('{path.as_posix()}')")
    names = [d[0] for d in cursor.description]
    _check_columns(spec, set(names))
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()], data


def _default_pair(
    specs: list[TableSpec], rows: dict[str, list[dict[str, Any]]]
) -> list[tuple[Any, ...]]:
    """Two players in the pool of every table of the sport, in the group with most of them, with
    the most sample in the first table (ties by player id): keys of the first table."""
    first = specs[0]
    common: set[tuple[Any, ...]] | None = None
    for s in specs:
        keys = {_key(s, r) for r in rows[s.table] if s.passes(r)}
        common = keys if common is None else common & keys
    assert common is not None
    sample = {_key(first, r): r[first.sample] for r in rows[first.table]}
    by_group: dict[Any, list[tuple[Any, ...]]] = {}
    for k in common:
        by_group.setdefault(k[2] if first.partition else None, []).append(k)
    best = min(by_group, key=lambda g: (-len(by_group[g]), str(g)))
    ranked = sorted(by_group[best], key=lambda k: (-sample[k], k))
    if len(ranked) < 2:
        raise ValueError(f"{first.sport}: fewer than two players in the pool of every table")
    return ranked[:2]


def _aliases(data_dir: Path) -> list[dict[str, int]]:
    files = sorted((data_dir / "bronze" / "basketball" / "player_id_aliases").glob("*.parquet"))
    if not files:
        raise FileNotFoundError("no bronze basketball player_id_aliases")
    con = duckdb.connect()
    pairs = {
        (a, c)
        for f in files
        for a, c in con.execute(
            f"SELECT player_id, canonical_player_id FROM read_parquet('{f.as_posix()}')"
        ).fetchall()
        if a != c
    }
    return [{"player_id": a, "canonical_player_id": c} for a, c in sorted(pairs)]


def build(
    web_data: Path, data_dir: Path, catalog: tuple[TableSpec, ...] = CATALOG
) -> dict[str, Any]:
    manifest = json.loads((web_data / "warehouse.json").read_text(encoding="utf-8"))
    files = {t["table"]: t["file"] for t in manifest["tables"]}
    con = duckdb.connect()
    rows: dict[str, list[dict[str, Any]]] = {}
    digest: dict[str, str] = {}
    for spec in catalog:
        if spec.table not in files:
            raise ValueError(f"{spec.table}: not in warehouse.json")
        rows[spec.table], data = _read(con, spec, web_data / "warehouse" / files[spec.table])
        digest[spec.table] = hashlib.sha256(data).hexdigest()

    pairs: dict[str, Any] = {}
    probes: dict[str, list[tuple[Any, ...]]] = {}
    for sport in SPORTS:
        specs = [s for s in catalog if s.sport == sport]
        if not specs:
            continue
        keys = _default_pair(specs, rows)
        for s in specs:
            probes[s.table] = keys
        first = specs[0]
        by_key = {_key(first, r): r for r in rows[first.table]}
        players = []
        for k in keys:
            r = by_key[k]
            p = dict(zip(first.key, k, strict=True))
            p["player_name"] = r["player_name"]
            p["team_name"] = r["team_name"]
            if sport == "football":
                p["age"] = r[AGE]
            players.append(p)
        pairs[sport] = players

    tables = []
    for spec in catalog:
        block = table_block(spec, rows[spec.table], probes[spec.table])
        tables.append(
            {
                "table": spec.table,
                "sport": spec.sport,
                "file": files[spec.table],
                "sha256": digest[spec.table],
                "key": list(spec.key),
                "sample": spec.sample,
                "floor": spec.floor_text,
                "rows_total": len(rows[spec.table]),
                "partition": spec.partition,
                "metrics": [
                    {"id": m.id, "expr": m.expr, "label": m.label, "scale": m.scale, "unit": m.unit}
                    for m in spec.metrics
                ],
                **block,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "age_reference": AGE_REFERENCE.isoformat(),
        "default_pairs": pairs,
        "aliases": _aliases(data_dir),
        "tables": tables,
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1) + "\n"


def run_publish_scouting(data_dir: Path, out_dir: Path, *, check: bool = False) -> int:
    try:
        text = render(build(out_dir, data_dir))
    except (FileNotFoundError, duckdb.IOException, ValueError) as error:
        print(f"publish scouting: {error}")
        return 1
    path = out_dir / SCOUTING_JSON
    if check:
        if not path.is_file() or path.read_bytes() != text.encode("utf-8"):
            print(f"publish scouting --check: {SCOUTING_JSON} differs from the published Parquet")
            return 1
        print(f"publish scouting --check: {SCOUTING_JSON} matches the published Parquet")
        return 0
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"publish scouting: {path} ({path.stat().st_size} bytes)")
    return 0
