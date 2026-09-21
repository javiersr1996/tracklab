"""What every bronze table shares: where the raw bytes are, where Parquet goes, how it is written.

Bronze is the provider in Parquet: native names, native rows, no filtering and no
derivation. The only transformations are type casts declared in the schema of each
table and documented next to it. This module fixes the conventions that every bronze
builder (basketball tracking and events, football tracking and CSV families) copies:

- Layout: one file per match and table, ``<data_dir>/bronze/<sport>/<table>/<match_id>.parquet``.
  The match id is also a column of every row, so the path is never load-bearing and
  ``read_parquet('.../<table>/*.parquet')`` reads a whole sport with plain column
  filters (each file holds a single match_id, so row-group statistics prune files).
- Lineage: every table starts with ``sport``, ``match_id``, ``source_file`` (the
  bundle-relative path of the raw file the row was read from) and ``source_row`` (the
  0-based position of the record in that file: line of a JSONL, index in a JSON array,
  data row of a CSV). ``source_row`` is not a frame or event number: in basketball
  tracking ``frameIdx`` jumps at every break, so line N is not frame N, and keeping
  both columns makes the difference visible instead of hiding it.
- Typing: a batch is built from named columns against the declared schema. A column
  missing, a column too many, a value that does not cast, or a null in a non-nullable
  field fails the run with the column's name; nothing is coerced in silence.
- Writing: ZSTD, 100k-row row groups, and atomic (temp file then rename) so an
  interrupted run never leaves a truncated file that still opens. The pinned commit
  and the sha256 of the raw file travel in the Parquet key-value metadata.
- Input: bronze reads the raw root that ``tracklab ingest`` verified, resolved from
  the receipt it wrote (``source_path`` when the bytes live in an outside clone).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from tracklab.ingest.fetch import RECEIPT_NAME

ROW_GROUP_ROWS = 100_000
COMPRESSION = "zstd"

LINEAGE_FIELDS: tuple[pa.Field, ...] = (
    pa.field("sport", pa.string(), nullable=False),
    pa.field("match_id", pa.int64(), nullable=False),
    pa.field("source_file", pa.string(), nullable=False),
    pa.field("source_row", pa.int64(), nullable=False),
)


def raw_root_for(data_dir: Path, source_id: str) -> Path:
    """Directory holding the verified raw bundle of ``source_id`` (its ``data/`` is inside).

    Read from the receipt ``tracklab ingest`` wrote: ``source_path`` when the bytes
    were verified in place inside an outside clone, else the receipt's own directory.
    A missing receipt or a receipt with failures means nothing verified is on disk.
    """
    receipt_dir = data_dir / "raw" / source_id
    receipt_path = receipt_dir / RECEIPT_NAME
    if not receipt_path.is_file():
        raise FileNotFoundError(
            f"{receipt_path} not found; run `tracklab ingest {source_id}` first"
        )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["failed"]:
        raise RuntimeError(
            f"{source_id}: {len(receipt['failed'])} file(s) failed verification; "
            f"re-run `tracklab ingest {source_id}`"
        )
    source_path = receipt.get("source_path")
    return Path(source_path) if source_path else receipt_dir


def bronze_path(data_dir: Path, sport: str, table: str, match_id: int) -> Path:
    return data_dir / "bronze" / sport / table / f"{match_id}.parquet"


def batch_from_columns(
    schema: pa.Schema, columns: Mapping[str, Sequence[Any] | Any], n_rows: int
) -> pa.RecordBatch:
    """A RecordBatch of ``schema`` from named columns, failing with the column's name.

    A value that is not a list is a per-batch constant (the lineage columns) and is
    repeated ``n_rows`` times.
    """
    missing = [f.name for f in schema if f.name not in columns]
    extra = sorted(set(columns) - set(schema.names))
    if missing or extra:
        raise ValueError(f"columns missing {missing}, unexpected {extra}")
    arrays: list[pa.Array] = []
    for field in schema:
        values = columns[field.name]
        try:
            if isinstance(values, list):
                array = pa.array(values, type=field.type)
            else:
                array = pa.repeat(pa.scalar(values, type=field.type), n_rows)
        except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError, TypeError) as exc:
            raise ValueError(f"column {field.name}: {exc}") from exc
        if len(array) != n_rows:
            raise ValueError(f"column {field.name}: {len(array)} values for {n_rows} rows")
        if not field.nullable and array.null_count:
            raise ValueError(f"column {field.name}: {array.null_count} null(s), declared NOT NULL")
        arrays.append(array)
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


class ParquetSink:
    """Writes batches of one declared schema to one Parquet file, atomically.

    The file only appears under its final name when the ``with`` block exits
    cleanly; on an exception the partial temp file is removed. ``rows`` and
    ``bytes`` are filled on exit.
    """

    def __init__(self, path: Path, schema: pa.Schema, metadata: Mapping[str, str]) -> None:
        self.path = path
        self.rows = 0
        self.bytes = 0
        self._tmp = path.with_name(path.name + ".tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._writer = pq.ParquetWriter(
            self._tmp, schema.with_metadata(dict(metadata)), compression=COMPRESSION
        )

    def __enter__(self) -> ParquetSink:
        return self

    def write(self, batch: pa.RecordBatch) -> None:
        if batch.num_rows == 0:
            return
        self._writer.write_batch(batch, row_group_size=ROW_GROUP_ROWS)
        self.rows += batch.num_rows

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._writer.close()
        if exc_type is not None:
            self._tmp.unlink(missing_ok=True)
            return
        os.replace(self._tmp, self.path)
        self.bytes = self.path.stat().st_size
