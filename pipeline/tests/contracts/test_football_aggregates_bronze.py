"""Contract of the bronze football season aggregates against the built Parquet.

Skipped when the bronze tables are not built under `data_root()`. Reads only the
artefact on disk, never what the builder computed in memory.
"""

from __future__ import annotations

import pyarrow.parquet as pq
import pytest

from tracklab.bronze.common import bronze_season_path, season_csv_schema
from tracklab.bronze.football.aggregates import SCHEMAS_DIR
from tracklab.formats.csvschema import load_schema
from tracklab.paths import data_root

SPORT = "football"

# docs/formats/football.md, "Season aggregates".
EXPECTED_ROWS = {"aggregates_obr": 407, "aggregates_passing": 407, "aggregates_physical": 406}

pytestmark = pytest.mark.skipif(
    not (data_root() / "bronze" / "football" / "aggregates_physical").is_dir(),
    reason="run `tracklab bronze football --tables aggregates` first",
)


def test_every_table_has_the_declared_schema() -> None:
    for table in EXPECTED_ROWS:
        frozen = load_schema(SCHEMAS_DIR / f"{table}.schema.json")
        declared = season_csv_schema(frozen)
        path = bronze_season_path(data_root(), SPORT, table)
        written = pq.read_schema(path)
        print(f"{table} columns={len(written)}")
        assert written.equals(declared, check_metadata=False), f"{table}: {written}"


def test_row_counts() -> None:
    print(f"\n{'table':>18} {'rows':>6}")
    counts = {}
    for table in EXPECTED_ROWS:
        path = bronze_season_path(data_root(), SPORT, table)
        n = pq.read_table(path).num_rows
        counts[table] = n
        print(f"{table:>18} {n:>6}")
    assert counts == EXPECTED_ROWS


def test_no_match_id_column_season_grain() -> None:
    for table in EXPECTED_ROWS:
        path = bronze_season_path(data_root(), SPORT, table)
        names = pq.read_schema(path).names
        assert "match_id" not in names, f"{table}: season grain must not carry match_id"
        assert names[:3] == ["sport", "source_file", "source_row"]
