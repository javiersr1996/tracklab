"""Bronze of the basketball season aggregates: ``aggregates_{shots,drives,picks}``.

Grain is player x team x season (no match dimension), so these three tables use
``SEASON_LINEAGE_FIELDS`` (``sport, source_file, source_row``, no ``match_id``) and
live at the season path (``bronze_season_path``), like ``player_id_aliases`` in
``meta.py``. Bronze does not sniff the CSVs: it loads the ``*.schema.json`` that
``tracklab freeze-schema basketball`` froze with ``freeze_csv_family`` and imposes it
with ``formats.csvschema.read_typed`` (DuckDB ``read_csv(columns=...)``, so a value
that does not parse fails here with the file name). Each file is at most a few
hundred rows, so it is read whole into pyarrow, no streaming.

The CSV-to-Parquet body (read typed, add lineage, write) is identical to football's
season aggregates, so it lives once in ``bronze.common.build_season_csv_table``; this
module only knows basketball's schemas directory and its 3 family names
(``formats.basketball.aggregate_table``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import duckdb

from tracklab.bronze.common import SeasonCsvStats, build_season_csv_table
from tracklab.formats.basketball import aggregate_table
from tracklab.formats.csvschema import load_schema
from tracklab.ingest.manifest import Source

SPORT = "basketball"
SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas" / "basketball"
Log = Callable[[str], None]


def build_aggregates(
    source: Source, raw_root: Path, data_dir: Path, log: Log = print
) -> list[SeasonCsvStats]:
    commit = source.commit
    if commit is None:
        raise RuntimeError(f"{source.source_id} is not frozen; run `tracklab freeze` first")
    entries = sorted((f for f in source.files if f.role == "aggregate"), key=lambda f: f.path)
    con = duckdb.connect()
    log(f"{'table':>17} {'rows':>6} {'seconds':>8} {'MB':>7}")
    stats: list[SeasonCsvStats] = []
    for entry in entries:
        table = aggregate_table(Path(entry.path))
        frozen = load_schema(SCHEMAS_DIR / f"{table}.schema.json")
        s = build_season_csv_table(SPORT, table, frozen, entry, raw_root, commit, data_dir, con)
        log(f"{s.table:>17} {s.rows:>6} {s.seconds:>8.2f} {s.mb:>7.2f}")
        stats.append(s)
    return stats
