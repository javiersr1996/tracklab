"""`tracklab publish stats`: `web/public/data/stats.json`, the figures the web
and the README are allowed to quote (task 17).

Row counts are not computed here a second time: `tracklab.silver.stats`
already counts every silver table per sport and match for `tracklab stats`,
and this module calls the same `count_table` over the same tables, so the two
commands can never disagree about a row count by construction rather than by
coincidence. What this module adds is the input/output byte totals: the
provider's bytes as the manifest pins them (sha256 and size per file) against
the JSON the web ships. Both are reproducible to the byte; the size of the
Parquet in between is not, because DuckDB's parallel writer lays out row groups
differently from run to run with the same rows.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from tracklab.ingest.manifest import load_manifest
from tracklab.silver.stats import count_table, silver_dir, silver_tables, table_glob

SPORTS = ("basketball", "football")


def raw_bytes(manifest_path: Path) -> dict[str, int]:
    """Every file of each source, as `tracklab freeze` pinned it."""
    by_sport = {
        source.sport: sum(f.bytes for f in source.files)
        for source in load_manifest(manifest_path).sources
    }
    return {**by_sport, "total": sum(by_sport.values())}


def published_bytes(out_dir: Path) -> dict[str, int]:
    """The possession files per sport, named by their `bb_`/`fb_` id."""
    files = list((out_dir / "possessions").glob("*.json"))
    by_sport = {
        sport: sum(p.stat().st_size for p in files if p.name.startswith(prefix))
        for sport, prefix in (("basketball", "bb_"), ("football", "fb_"))
    }
    return {**by_sport, "total": sum(by_sport.values())}


def stats_path(out_dir: Path) -> Path:
    return out_dir / "stats.json"


def run_publish_stats(
    data_dir: Path, out_dir: Path, manifest_path: Path = Path("manifest/sources.json")
) -> int:
    present = silver_tables(data_dir)
    if not present:
        print(f"publish stats: no silver table under {silver_dir(data_dir)}; run dbt build first")
        return 1

    con = duckdb.connect()
    tables: list[dict[str, Any]] = []
    for table, partitioned in present:
        source = table_glob(data_dir, table)
        for count in count_table(con, table, source, per_match=partitioned):
            tables.append(
                {
                    "table": count.table,
                    "sport": count.sport,
                    "match_id": count.match_id,
                    "rows": count.rows,
                }
            )

    payload = {
        "schema_version": 1,
        "tables": tables,
        "bytes": {
            "raw": raw_bytes(manifest_path),
            "published": published_bytes(out_dir),
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    path = stats_path(out_dir)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"publish stats: {len(tables)} rows across {len(present)} tables, {path}")
    print(f"publish stats: {path} ({path.stat().st_size} bytes)")
    return 0
