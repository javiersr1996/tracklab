"""`web/public/data/stats.json` against `tracklab.silver.stats`, the module it
is supposed to reuse rather than re-count (task 17). Skipped when the real
silver build or the published `stats.json` are not there, same as
`tests/contracts`.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from tracklab.silver.stats import count_table, silver_tables, table_glob

PIPELINE = Path(__file__).resolve().parents[2]
REPO_ROOT = PIPELINE.parent
DATA = PIPELINE / "data"
STATS_PATH = REPO_ROOT / "web" / "public" / "data" / "stats.json"

pytestmark = pytest.mark.skipif(
    not DATA.is_dir() or not STATS_PATH.is_file(),
    reason="pipeline/data or web/public/data/stats.json missing; "
    "run `tracklab publish stats` over a real build",
)


def test_rows_match_what_tracklab_silver_stats_computes() -> None:
    payload = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    published = {
        (row["table"], row["sport"], row["match_id"], row["rows"]) for row in payload["tables"]
    }

    con = duckdb.connect()
    expected = set()
    for table, partitioned in silver_tables(DATA):
        for count in count_table(con, table, table_glob(DATA, table), per_match=partitioned):
            expected.add((count.table, count.sport, count.match_id, count.rows))

    print(f"published {len(published)} rows, tracklab.silver.stats computes {len(expected)}")
    assert published == expected


def test_bytes_come_from_the_manifest_and_the_published_files() -> None:
    payload = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    raw, published = payload["bytes"]["raw"], payload["bytes"]["published"]
    print(f"raw: {raw}")
    print(f"published: {published}")

    manifest = json.loads(Path("manifest/sources.json").read_text(encoding="utf-8"))
    pinned = sum(f["bytes"] for source in manifest["sources"] for f in source["files"])
    shipped = sum(p.stat().st_size for p in (STATS_PATH.parent / "possessions").glob("*.json"))
    assert raw["total"] == pinned
    assert published["total"] == shipped
    assert raw["basketball"] + raw["football"] == raw["total"]
    assert published["basketball"] + published["football"] == shipped
