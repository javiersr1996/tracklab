"""Bronze of the basketball events: the 20 ``events_<family>`` tables.

``dynamic_events.json`` is a dict of 20 families (chances, possessions, shots, ...),
each a JSON array of same-shaped records. Bronze does not sniff this file: it loads
the ``*.schema.json`` that ``tracklab freeze-schema basketball`` froze
(``tracklab.formats.basketball``) and IMPOSES it, exactly as tracking imposes its
pyarrow schema and CSV bronze imposes ``FrozenSchema``. A key missing, a key extra, or
a value that does not cast fails the run naming the file, the family and the row.

One Parquet per match and family, written whole (each raw file is at most a few MB, so
there is no reason to stream). Two things this module owns and nothing else does:

- ``gameId`` inside every event row is checked against the match id of the file it
  came from: the provider never disagrees in this bundle (0 discrepancies over about
  76,000 rows, measured while freezing), and a future disagreement must fail loudly
  here rather than silently mislabel a row.
- The one declared cast (``closeouts.touchWallClock``, VARCHAR -> BIGINT) is applied
  from the frozen column's ``source_type``/``type`` pair, through ``_cast_value``: a
  cast this module does not know how to perform fails instead of being skipped.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa

from tracklab.bronze.common import ParquetSink, batch_from_columns, bronze_path
from tracklab.formats.basketball import (
    FAMILY_ORDER,
    SCALAR_PA_TYPES,
    FrozenFamily,
    Log,
    load_family,
    pa_schema,
)
from tracklab.ingest.manifest import FileEntry, Source

SPORT = "basketball"
SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas" / "basketball"


@dataclass(frozen=True)
class EventsStats:
    match_id: int
    family: str
    rows: int
    seconds: float
    mb: float


def load_frozen_families(schemas_dir: Path = SCHEMAS_DIR) -> dict[str, FrozenFamily]:
    return {
        family: load_family(schemas_dir / f"events_{family}.schema.json") for family in FAMILY_ORDER
    }


def _cast_value(value: Any, source_type: str | None, stored_type: str) -> Any:
    if value is None or source_type is None:
        return value
    if source_type == "VARCHAR" and stored_type == "BIGINT":
        return int(value)
    raise ValueError(f"no declared cast from {source_type} to {stored_type}")


def family_batch(
    frozen: FrozenFamily,
    schema: pa.Schema,
    rows: list[dict[str, Any]],
    match_id: int,
    source_file: str,
) -> pa.RecordBatch:
    """One ``events_<family>`` batch: lineage plus the frozen columns, POINT2D split
    into ``<key>_x``/``<key>_y``, ``source_row`` the 0-based position in ``rows``.

    Imposes, never infers: every row's key set is checked against the frozen columns
    before anything is read from it, so a key the provider added or dropped since the
    freeze fails here naming the file, the family, the row and the keys, instead of
    being silently dropped (extra) or raising a bare ``KeyError`` (missing).
    """
    expected_keys = frozenset(c.name for c in frozen.columns)
    pa_types = {c.name: SCALAR_PA_TYPES[c.type] for c in frozen.columns if c.type != "POINT2D"}
    columns: dict[str, Any] = {
        "sport": SPORT,
        "match_id": match_id,
        "source_file": source_file,
        "source_row": list(range(len(rows))),
    }
    for column in frozen.columns:
        if column.type == "POINT2D":
            columns[f"{column.name}_x"] = []
            columns[f"{column.name}_y"] = []
        else:
            columns[column.name] = []

    for i, row in enumerate(rows):
        keys = row.keys()
        if keys != expected_keys:
            raise ValueError(
                f"{source_file} {frozen.family}[{i}]: missing {sorted(expected_keys - keys)}, "
                f"extra {sorted(keys - expected_keys)}"
            )
        if row["gameId"] != match_id:
            raise ValueError(
                f"{source_file} {frozen.family}[{i}]: gameId {row['gameId']} != {match_id}"
            )
        for column in frozen.columns:
            value = row[column.name]
            try:
                if column.type == "POINT2D":
                    columns[f"{column.name}_x"].append(None if value is None else float(value[0]))
                    columns[f"{column.name}_y"].append(None if value is None else float(value[1]))
                    continue
                casted = _cast_value(value, column.source_type, column.type)
                if casted is not None:
                    pa.scalar(casted, type=pa_types[column.name])  # raises if it will not fit
                columns[column.name].append(casted)
            except (
                TypeError,
                ValueError,
                IndexError,
                pa.lib.ArrowInvalid,
                pa.lib.ArrowTypeError,
            ) as exc:
                raise ValueError(
                    f"{source_file} {frozen.family}[{i}].{column.name}: {exc}"
                ) from exc
    return batch_from_columns(schema, columns, len(rows))


def build_events_match(
    entry: FileEntry,
    raw_root: Path,
    data_dir: Path,
    commit: str,
    families: dict[str, FrozenFamily],
    schemas: dict[str, pa.Schema],
) -> list[EventsStats]:
    """Write ``events_<family>/<match_id>.parquet`` of every family for one match."""
    assert entry.match_id is not None
    data = json.loads((raw_root / entry.path).read_text(encoding="utf-8"))
    found, expected = set(data.keys()), set(FAMILY_ORDER)
    if found != expected:
        raise ValueError(
            f"{entry.path}: families missing {sorted(expected - found)}, "
            f"extra {sorted(found - expected)}"
        )
    metadata = {
        "tracklab.sport": SPORT,
        "tracklab.source_file": entry.path,
        "tracklab.source_sha256": entry.sha256,
        "tracklab.source_commit": commit,
    }
    stats = []
    for family in FAMILY_ORDER:
        started = time.perf_counter()
        batch = family_batch(
            families[family], schemas[family], data[family], entry.match_id, entry.path
        )
        path = bronze_path(data_dir, SPORT, f"events_{family}", entry.match_id)
        with ParquetSink(path, schemas[family], metadata) as sink:
            sink.write(batch)
        stats.append(
            EventsStats(
                entry.match_id, family, sink.rows, time.perf_counter() - started, sink.bytes / 1e6
            )
        )
    return stats


def build_events(
    source: Source, raw_root: Path, data_dir: Path, log: Log = print
) -> list[EventsStats]:
    """Every ``events_<family>`` table of every match, in match id then family order."""
    if source.commit is None:
        raise RuntimeError(f"{source.source_id} is not frozen; run `tracklab freeze` first")
    families = load_frozen_families()
    schemas = {family: pa_schema(frozen) for family, frozen in families.items()}
    entries = sorted(
        (f for f in source.files if f.role == "events" and f.match_id is not None),
        key=lambda f: f.match_id or 0,
    )
    log(f"{'match_id':>8} {'family':>17} {'rows':>6} {'seconds':>8} {'MB':>7}")
    all_stats: list[EventsStats] = []
    for entry in entries:
        for s in build_events_match(entry, raw_root, data_dir, source.commit, families, schemas):
            log(f"{s.match_id:>8} {s.family:>17} {s.rows:>6} {s.seconds:>8.2f} {s.mb:>7.2f}")
            all_stats.append(s)
    return all_stats
