"""Bronze of the football season aggregates: ``aggregates_{physical,obr,passing}``.

Grain is player x season (no match dimension, docs/formats/football.md "Season
aggregates"), so these three tables use ``SEASON_LINEAGE_FIELDS`` and
``bronze_season_path``, exactly as basketball's ``aggregates_{shots,drives,picks}``
(``bronze/basketball/aggregates.py``). The two builders share one body,
``bronze.common.build_season_csv_table`` (read the frozen ``*.schema.json`` whole
with ``formats.csvschema.read_typed``, add lineage, write); this module only knows
football's schemas directory and its 3 family names.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import duckdb

from tracklab.bronze.common import SeasonCsvStats, build_season_csv_table
from tracklab.formats.csvschema import load_schema
from tracklab.ingest.manifest import Source

SPORT = "football"
SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas" / "football"
Log = Callable[[str], None]

# The 3 season aggregate files this bundle ships (docs/formats/football.md, "Season
# aggregates"): data/aggregates/aus1league_<family>aggregates_20242025.csv.
AGGREGATE_FAMILIES: tuple[str, ...] = ("physical", "obr", "passing")


def aggregate_table(path: Path) -> str:
    """`aggregates_<family>` for a raw football aggregate CSV path."""
    for family in AGGREGATE_FAMILIES:
        if f"_{family}aggregates_" in path.name:
            return f"aggregates_{family}"
    raise ValueError(f"unrecognised football aggregate file: {path.name}")


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
