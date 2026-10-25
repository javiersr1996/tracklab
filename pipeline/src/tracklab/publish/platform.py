"""`tracklab publish platform`: `web/public/data/platform.json`, the manifest
`/platform` (task 35) draws its layers, tables and per-match numbers from
(task 34). Every figure comes from
the newest `tracklab build` record under `<data root>/build/` (or `--run PATH`) --
the same JSON task 32 writes, rows from Parquet footers and bytes from
`stat` -- except the published bytes (`disk.publish`), which are measured live on
`web/public/data` by `build.measure_publish` on every run and every `--check`, because a
record taken before a later commit added JSON there would otherwise go stale unnoticed
-- plus `web/public/data/index.json`, the six curated possessions'
own index (task 17), for `matches[].published_*`.

Two decisions, not forced.

1. **The title is circular unless "out" comes from the record.** `title =
   f"{fmt(bytes_pinned)} in, {fmt(bytes_published)} out"`, and the obvious
   reading of "bytes out" -- rescan `web/public/data` right now -- cannot
   work: `platform.json` itself lives in that directory, so its size would
   depend on the title string, which depends on its size. `layers[].publish`
   uses `disk.publish` from the build record instead, and `tracklab build`
   leaves `lineage.json` and this file out of that measurement by name
   (`build.ABOUT_PLATFORM`): the `build` job writes neither, they describe
   the platform (its graph, its measure) rather than the data it publishes,
   and this file counted would make each title depend on the previous run's.
   Excluding them by when the measurement happened held only for the first
   record; every later one found them on disk. The `note` on that layer says so, so a
   reader of the JSON does not have to already know it.
2. **Files with no match.** `season_files` holds every raw manifest entry
   whose `match_id` is `None` (season aggregates, `matches.json`, the
   basketball player-alias table, the football body-pose sample):
   `sum(matches[].raw_bytes) + season_files.bytes == layers.raw.bytes_pinned`
   is the reconciliation a test proves, and the same holds for
   `bytes_read` against `layers.raw.bytes_read`. `bronze/common/orientation` and the
   season-only bronze tables (`matches`, `player_id_aliases`,
   `aggregates_*`) are never attributed to a match for the same reason, but
   structurally rather than by a second exclusion list: `matches[]` only
   ever reads `tracking_frames`'s per-match file names and `frames`/`events`'
   `native_match_id=` partitions, so a season table simply never has a match
   id to be found under.

`--check` writes nothing. It compares the published layer, title and subtitle (files,
bytes to watch and to query, live) and row counts -- never the bytes of the Parquet tables, because
`publish/stats.py` already documents that DuckDB's parallel writer lays out
Parquet row groups differently run to run, so byte counts are not
reproducible even though row counts are -- by table against the given
record, and by match against `web/public/data/stats.json` when it is
present, an independent count (`silver/stats.py`'s own `duckdb` query, not
this module's Parquet-footer reading) so the two can actually disagree
instead of agreeing by construction.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tracklab.publish.format import fmt

SCHEMA_VERSION = 1
PLATFORM_JSON = "platform.json"
INDEX_JSON = "index.json"
STATS_JSON = "stats.json"

TRACKING_TABLE = "tracking_frames"
FRAMES_TABLE = "frames"
EVENTS_TABLE = "events"
SPORTS = ("basketball", "football")

GROUP_TO_LAYER = {
    "ingest": "raw",
    "bronze": "bronze",
    "silver": "silver",
    "gold": "gold",
    "quality": "quality",
    "publish": "publish",
}
LAYER_ORDER = ("raw", "bronze", "silver", "gold", "quality", "publish")

_MATCH_FILE = re.compile(r"^(\d+)\.parquet$")
_NATIVE_PARTITION = re.compile(r"native_match_id=(\d+)")


def latest_record(record_dir: Path) -> Path:
    records = sorted(record_dir.glob("*.json"))
    if not records:
        raise FileNotFoundError(f"no build record under {record_dir}; run `tracklab build` first")
    return records[-1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


# --- layers ------------------------------------------------------------------------


def _step_seconds(steps: list[dict[str, Any]]) -> dict[str, tuple[float | None, float]]:
    """Per layer: the slowest step's seconds (what a reader should weigh
    against the wall clock) and the sum of every step's seconds, informative
    only -- steps in the same layer can run in parallel, so the sum is not a
    second wall-clock estimate (task 32's own record says as much)."""
    by_layer: dict[str, list[float]] = {layer: [] for layer in LAYER_ORDER}
    for step in steps:
        if step["duration_ms"] is None:
            continue
        layer = GROUP_TO_LAYER.get(step["group"])
        if layer is None:
            continue
        by_layer[layer].append(step["duration_ms"] / 1000.0)
    return {
        layer: (round(max(seconds), 1) if seconds else None, round(sum(seconds), 1))
        for layer, seconds in by_layer.items()
    }


def layers_from_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    disk = record["disk"]
    raw, bronze, silver, gold, quality, publish = (
        disk["raw"],
        disk["bronze"],
        disk["silver"],
        disk["gold"],
        disk["quality"],
        disk["publish"],
    )
    rows_by_layer: dict[str, int | None] = {
        "raw": None,
        "bronze": bronze["rows"],
        "silver": silver["rows"],
        "gold": gold["rows"],
        "quality": quality["rows"],
        "publish": None,
    }
    files_by_layer = {
        "raw": raw["files"],
        "bronze": bronze["files"],
        "silver": silver["files"],
        "gold": gold["files"],
        "quality": quality["files"],
        "publish": publish["files"],
    }
    bytes_by_layer = {
        "raw": raw["bytes_pinned"],
        "bronze": bronze["bytes"],
        "silver": silver["bytes"],
        "gold": gold["bytes"],
        "quality": quality["bytes"],
        "publish": publish["bytes"],
    }
    seconds_by_layer = _step_seconds(record["steps"])

    layers = []
    for layer in LAYER_ORDER:
        seconds, seconds_sum = seconds_by_layer[layer]
        entry: dict[str, Any] = {
            "layer": layer,
            "files": files_by_layer[layer],
            "rows": rows_by_layer[layer],
            "bytes": bytes_by_layer[layer],
            "seconds": seconds,
            "seconds_sum": seconds_sum,
        }
        if layer == "raw":
            entry["bytes_pinned"] = raw["bytes_pinned"]
            entry["bytes_read"] = raw["bytes_read"]
            entry["downloaded"] = raw["downloaded"]
            entry["verified"] = raw["verified"]
        if layer == "publish":
            entry["watch_files"] = len(publish["watch"])
            entry["watch_bytes"] = publish["watch_bytes"]
            entry["query_files"] = len(publish["query"])
            entry["query_bytes"] = publish["query_bytes"]
            entry["note"] = (
                "split by use: to watch, the possessions and the JSON the other pages are built "
                "from; to query, what only /warehouse uses, the Parquet and the warehouse*.json "
                "that describe them; as `tracklab build` "
                "measured them, without lineage.json and platform.json (counting platform.json "
                "would make the title depend on its own previous value, decision 1); the query "
                "engine is not data and is not counted"
            )
        layers.append(entry)
    return layers


# --- tables ------------------------------------------------------------------------


def tables_from_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    disk = record["disk"]
    rows = [
        {
            "layer": t["layer"],
            "sport": t["sport"],
            "table": t["table"],
            "files": t["files"],
            "rows": t["rows"],
            "bytes": t["bytes"],
        }
        for t in (*disk["bronze"]["tables"], *disk["silver"]["tables"], *disk["gold"]["tables"])
    ]
    rows.sort(key=lambda r: (r["layer"], r["sport"] or "", r["table"]))
    return rows


# --- season files: no match to attribute them to ------------------------------------


def season_files_from_record(record: dict[str, Any]) -> dict[str, Any]:
    items = [
        {
            "sport": source["sport"],
            "role": f["role"],
            "path": f["path"],
            "bytes": f["bytes"],
            "bytes_read": f["bytes_read"] or 0,
        }
        for source in record["disk"]["raw"]["sources"]
        for f in source["manifest"]
        if f["match_id"] is None
    ]
    items.sort(key=lambda i: (i["sport"], i["path"]))
    return {
        "files": len(items),
        "bytes": sum(i["bytes"] for i in items),
        "bytes_read": sum(i["bytes_read"] for i in items),
        "items": items,
    }


# --- raw sources: where the "in" comes from, one row per ingest source ------------------


def raw_sources_from_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """`disk.raw.sources[]`, the same per-source pins `bytes_pinned` is the sum of, so
    `sum(raw_sources[].bytes) == layers.raw.bytes_pinned` by the record's own construction
    (and a test proves it). `/platform` reads the P6 body-pose share from here, not from prose."""
    return [
        {
            "source_id": s["source_id"],
            "sport": s["sport"],
            "files": s["files"],
            "bytes": s["bytes_pinned"],
        }
        for s in record["disk"]["raw"]["sources"]
    ]


# --- matches: raw bytes from the manifest, bronze from the filename, silver from the
# --- partition ------------------------------------------------------------------


def _raw_match_totals(record: dict[str, Any]) -> dict[tuple[str, int], dict[str, int]]:
    totals: dict[tuple[str, int], dict[str, int]] = {}
    for source in record["disk"]["raw"]["sources"]:
        sport = source["sport"]
        for f in source["manifest"]:
            match_id = f["match_id"]
            if match_id is None:
                continue
            entry = totals.setdefault((sport, match_id), {"raw_bytes": 0, "raw_bytes_read": 0})
            entry["raw_bytes"] += f["bytes"]
            entry["raw_bytes_read"] += f["bytes_read"] or 0
    return totals


def _bronze_table(record: dict[str, Any], sport: str, table: str) -> dict[str, Any] | None:
    tables: list[dict[str, Any]] = record["disk"]["bronze"]["tables"]
    for t in tables:
        if t["sport"] == sport and t["table"] == table:
            return t
    return None


def _silver_table(record: dict[str, Any], table: str) -> dict[str, Any] | None:
    tables: list[dict[str, Any]] = record["disk"]["silver"]["tables"]
    for t in tables:
        if t["table"] == table:
            return t
    return None


def _bronze_rows_by_match(record: dict[str, Any], sport: str, table: str) -> dict[int, int]:
    """A bronze table's per-match rows, from its files literally named
    `<match_id>.parquet` -- never from a season table's single `data.parquet`,
    which this pattern does not match at all."""
    found = _bronze_table(record, sport, table)
    rows: dict[int, int] = {}
    if found is None:
        return rows
    for f in found["parquet"]:
        m = _MATCH_FILE.match(f["path"])
        if m:
            match_id = int(m.group(1))
            rows[match_id] = rows.get(match_id, 0) + f["rows"]
    return rows


def _silver_rows_by_match(record: dict[str, Any], sport: str, table: str) -> dict[int, int]:
    """A silver table's per-match rows, from its `sport=<sport>/
    native_match_id=<id>/` partitions -- absent for a table with no such
    partition, e.g. `dim_match`, which is season-level and never appears
    here."""
    found = _silver_table(record, table)
    rows: dict[int, int] = {}
    if found is None:
        return rows
    prefix = f"sport={sport}/"
    for f in found["parquet"]:
        if not f["path"].startswith(prefix):
            continue
        m = _NATIVE_PARTITION.search(f["path"])
        if m:
            match_id = int(m.group(1))
            rows[match_id] = rows.get(match_id, 0) + f["rows"]
    return rows


def _possessions_by_match(index_payload: dict[str, Any]) -> dict[tuple[str, int], dict[str, int]]:
    totals: dict[tuple[str, int], dict[str, int]] = {}
    for entry in index_payload.get("possessions", []):
        sport = entry["sport"]
        native = int(entry["match_id"].split(":")[1])
        agg = totals.setdefault((sport, native), {"n": 0, "bytes": 0})
        agg["n"] += 1
        agg["bytes"] += entry["bytes"]
    return totals


def matches_from_record(
    record: dict[str, Any], index_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    raw_totals = _raw_match_totals(record)
    bronze_by_sport = {s: _bronze_rows_by_match(record, s, TRACKING_TABLE) for s in SPORTS}
    frames_by_sport = {s: _silver_rows_by_match(record, s, FRAMES_TABLE) for s in SPORTS}
    events_by_sport = {s: _silver_rows_by_match(record, s, EVENTS_TABLE) for s in SPORTS}
    published = _possessions_by_match(index_payload)

    rows = []
    for (sport, match_id), raw in raw_totals.items():
        pub = published.get((sport, match_id), {"n": 0, "bytes": 0})
        rows.append(
            {
                "sport": sport,
                "match_id": match_id,
                "raw_bytes": raw["raw_bytes"],
                "raw_bytes_read": raw["raw_bytes_read"],
                "bronze_tracking_rows": bronze_by_sport[sport].get(match_id, 0),
                "silver_frames_rows": frames_by_sport[sport].get(match_id, 0),
                "silver_events_rows": events_by_sport[sport].get(match_id, 0),
                "published_possessions": pub["n"],
                "published_bytes": pub["bytes"],
            }
        )
    rows.sort(key=lambda r: (r["sport"], r["match_id"]))
    return rows


# --- the payload ---------------------------------------------------------------------


def title_from_record(record: dict[str, Any]) -> str:
    return (
        f"{fmt(record['disk']['raw']['bytes_pinned'])} in, "
        f"{fmt(record['disk']['publish']['bytes'])} out"
    )


def subtitle_from_record(record: dict[str, Any]) -> str:
    """The split behind "out" (decision 10, option C), by use (`build.serves_query`): what the
    site watches and what `/warehouse` queries, from the same measure as the title."""
    publish = record["disk"]["publish"]
    return f"{fmt(publish['watch_bytes'])} to watch, {fmt(publish['query_bytes'])} to query"


def run_block(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "git_sha": record["git_sha"],
        "started_utc": record["started_utc"],
        "finished_utc": record["finished_utc"],
        "wall_seconds": record["wall_seconds"],
        "host": record["host"],
        "versions": record["versions"],
    }


def platform_from_record(record: dict[str, Any], index_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "title": title_from_record(record),
        "subtitle": subtitle_from_record(record),
        "run": run_block(record),
        "layers": layers_from_record(record),
        "raw_sources": raw_sources_from_record(record),
        "steps": record["steps"],
        "tables": tables_from_record(record),
        "matches": matches_from_record(record, index_payload),
        "season_files": season_files_from_record(record),
    }


def platform_path(out_dir: Path) -> Path:
    return out_dir / PLATFORM_JSON


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# --- --check: rows by table and by match, against the record and stats.json ---------


def _stats_match_rows(stats_payload: dict[str, Any]) -> dict[tuple[str, int, str], int]:
    rows: dict[tuple[str, int, str], int] = {}
    for row in stats_payload.get("tables", []):
        if row["table"] not in (FRAMES_TABLE, EVENTS_TABLE) or not row["match_id"]:
            continue
        native = int(row["match_id"].split(":")[1])
        rows[(row["sport"], native, row["table"])] = row["rows"]
    return rows


def _diff_tables(on_disk: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[str]:
    disk_rows = {(t["layer"], t["sport"], t["table"]): t["rows"] for t in on_disk}
    problems = []
    for t in fresh:
        key = (t["layer"], t["sport"], t["table"])
        disk_value = disk_rows.get(key)
        if disk_value != t["rows"]:
            problems.append(f"table {key}: platform.json rows={disk_value} record rows={t['rows']}")
    return problems


def _diff_matches(
    on_disk: list[dict[str, Any]],
    fresh: list[dict[str, Any]],
    stats_rows: dict[tuple[str, int, str], int] | None,
) -> list[str]:
    disk_by_key = {(m["sport"], m["match_id"]): m for m in on_disk}
    fields = ("bronze_tracking_rows", "silver_frames_rows", "silver_events_rows")
    problems = []
    for m in fresh:
        key = (m["sport"], m["match_id"])
        disk_m = disk_by_key.get(key)
        for field in fields:
            disk_value = disk_m.get(field) if disk_m else None
            if disk_value != m[field]:
                problems.append(
                    f"match {key} {field}: platform.json={disk_value} record={m[field]}"
                )
        if stats_rows is None:
            continue
        for field, table in (
            ("silver_frames_rows", FRAMES_TABLE),
            ("silver_events_rows", EVENTS_TABLE),
        ):
            expected = stats_rows.get((*key, table))
            if expected is not None and expected != m[field]:
                problems.append(f"match {key} {field}: record={m[field]} stats.json={expected}")
    return problems


def run_publish_platform(
    *,
    record_path: Path | None,
    record_dir: Path,
    out_dir: Path,
    check: bool = False,
) -> int:
    path = record_path or latest_record(record_dir)
    record = load_json(path)
    if "error" in record["disk"]:
        print(
            f"publish platform: record {path.name} has no disk measure: {record['disk']['error']}"
        )
        return 1
    index_path = out_dir / INDEX_JSON
    index_payload = load_json(index_path) if index_path.is_file() else {"possessions": []}
    from tracklab.build import measure_publish  # build imports PLATFORM_JSON from here

    record["disk"]["publish"] = measure_publish(out_dir)
    payload = platform_from_record(record, index_payload)

    print(f"publish platform: record {path.name}")
    print(f"publish platform: title: {payload['title']}")
    print(f"publish platform: subtitle: {payload['subtitle']}")

    if check:
        target = platform_path(out_dir)
        if not target.is_file():
            print(f"publish platform --check: {target} missing")
            return 1
        on_disk = load_json(target)
        stats_path = out_dir / STATS_JSON
        stats_rows = _stats_match_rows(load_json(stats_path)) if stats_path.is_file() else None
        problems = _diff_tables(on_disk.get("tables", []), payload["tables"]) + _diff_matches(
            on_disk.get("matches", []), payload["matches"], stats_rows
        )
        for field in ("title", "subtitle"):
            if on_disk.get(field) != payload[field]:
                problems.append(f"{field}: on disk {on_disk.get(field)!r}, live {payload[field]!r}")
        # The seconds are the timing of whichever run built the record, not a measure of the
        # files: a fresh build on the runner never repeats them.
        timing = ("seconds", "seconds_sum")
        disk_publish = next((x for x in on_disk.get("layers", []) if x["layer"] == "publish"), None)
        live_publish = next(x for x in payload["layers"] if x["layer"] == "publish")
        if disk_publish is None or {k: v for k, v in disk_publish.items() if k not in timing} != {
            k: v for k, v in live_publish.items() if k not in timing
        }:
            problems.append(f"layers[publish]: on disk {disk_publish}, live {live_publish}")
        if on_disk.get("raw_sources") != payload["raw_sources"]:
            problems.append(
                f"raw_sources: on disk {on_disk.get('raw_sources')},"
                f" record {payload['raw_sources']}"
            )
        if problems:
            detail = "\n  ".join(problems)
            print(
                f"publish platform --check: {target} differs, {len(problems)} row(s):\n  {detail}"
            )
            return 1
        print(f"publish platform --check: {target} matches ({len(payload['matches'])} matches)")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = platform_path(out_dir)
    out_path.write_text(render(payload), encoding="utf-8", newline="\n")
    print(f"publish platform: {out_path} ({out_path.stat().st_size} bytes)")
    return 0
