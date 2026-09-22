"""Bronze of the basketball season aggregates: ``aggregates_{shots,drives,picks}``.

Grain is player x team x season (no match dimension), so these three tables use
``SEASON_LINEAGE_FIELDS`` (``sport, source_file, source_row``, no ``match_id``) and
live at the season path (``bronze_season_path``), like ``player_id_aliases`` in
``meta.py``. Bronze does not sniff the CSVs: it loads the ``*.schema.json`` that
``tracklab freeze-schema basketball`` froze with ``freeze_csv_family`` and imposes it
with ``formats.csvschema.read_typed`` (DuckDB ``read_csv(columns=...)``, so a value
that does not parse fails here with the file name). Each file is at most a few
hundred rows, so it is read whole into pyarrow, no streaming.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from tracklab.bronze.common import (
    SEASON_LINEAGE_FIELDS,
    ParquetSink,
    batch_from_columns,
    bronze_season_path,
)
from tracklab.formats.basketball import aggregate_table
from tracklab.formats.csvschema import load_schema, pa_schema, read_typed
from tracklab.ingest.manifest import FileEntry, Source

SPORT = "basketball"
SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas" / "basketball"
Log = Callable[[str], None]


@dataclass(frozen=True)
class AggregateStats:
    table: str
    rows: int
    seconds: float
    mb: float


def build_aggregate_table(
    table: str,
    entry: FileEntry,
    raw_root: Path,
    commit: str,
    data_dir: Path,
    con: duckdb.DuckDBPyConnection,
) -> AggregateStats:
    started = time.perf_counter()
    frozen = load_schema(SCHEMAS_DIR / f"{table}.schema.json")
    schema = pa.schema([*SEASON_LINEAGE_FIELDS, *pa_schema(frozen)])
    data = read_typed(frozen, raw_root / entry.path, con)
    n = data.num_rows
    columns: dict[str, Any] = {
        "sport": SPORT,
        "source_file": entry.path,
        "source_row": list(range(n)),
        **{name: data.column(name).to_pylist() for name in data.column_names},
    }
    batch = batch_from_columns(schema, columns, n)
    metadata = {
        "tracklab.sport": SPORT,
        "tracklab.source_file": entry.path,
        "tracklab.source_sha256": entry.sha256,
        "tracklab.source_commit": commit,
    }
    out_path = bronze_season_path(data_dir, SPORT, table)
    with ParquetSink(out_path, schema, metadata) as sink:
        sink.write(batch)
    return AggregateStats(table, sink.rows, time.perf_counter() - started, sink.bytes / 1e6)


def build_aggregates(
    source: Source, raw_root: Path, data_dir: Path, log: Log = print
) -> list[AggregateStats]:
    commit = source.commit
    if commit is None:
        raise RuntimeError(f"{source.source_id} is not frozen; run `tracklab freeze` first")
    entries = sorted((f for f in source.files if f.role == "aggregate"), key=lambda f: f.path)
    con = duckdb.connect()
    log(f"{'table':>17} {'rows':>6} {'seconds':>8} {'MB':>7}")
    stats: list[AggregateStats] = []
    for entry in entries:
        table = aggregate_table(Path(entry.path))
        s = build_aggregate_table(table, entry, raw_root, commit, data_dir, con)
        log(f"{s.table:>17} {s.rows:>6} {s.seconds:>8.2f} {s.mb:>7.2f}")
        stats.append(s)
    return stats
