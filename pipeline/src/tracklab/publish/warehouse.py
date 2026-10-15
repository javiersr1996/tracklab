"""`tracklab publish warehouse`: the Parquet files the browser reads, and
`web/public/data/warehouse.json`, which describes them (task 41, P4).

Gold is read with DuckDB and written with pyarrow, in a fixed row order, with a
fixed compression and row group size: the bytes are reproducible, which is what
lets the files live in git (Vercel builds from it) and a clean clone leave no
diff. DuckDB's own `COPY` is not used for the write: its parallel writer lays
row groups out differently from run to run (see `publish/stats.py`) and it
stamps its own `created_by`, which `warehouse.json` pins to the pyarrow version.

Each file is named `<table>.<sha8>.parquet`, so a URL never changes bytes
between deploys (decision 3 of the P4 plan). Publishing deletes the files of an
older hash, and only those: exact pattern, only inside the warehouse directory.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

WAREHOUSE_JSON = "warehouse.json"
WAREHOUSE_DIR = "warehouse"

# The wide tables the visitor queries (gold `agg_*`) and the long fact table. `table` is the
# short name the page will register (`bb_shots`, `fact`, ...); `model` is the gold model.
TABLES: tuple[tuple[str, str, str], ...] = (
    ("bb_drives", "agg_bb_drives", "basketball"),
    ("bb_picks", "agg_bb_picks", "basketball"),
    ("bb_shots", "agg_bb_shots", "basketball"),
    ("fb_obr", "agg_fb_obr", "football"),
    ("fb_passing", "agg_fb_passing", "football"),
    ("fb_physical", "agg_fb_physical", "football"),
    ("fact", "fact_player_season_metric", "both"),
)
FACT = "fact"

# Confirmed by Javier on 2026-10-08 with task 38's measurements in front of him
# (pipeline/reports/warehouse_probe.json, decision 9 in tasks/todo.md): of the layouts the
# DuckDB-WASM probe read, these read the fewest bytes per query, for the fact and the wide tables.
# The only place they are defined; change them here and `warehouse.json` follows.
#
# Wide tables: sorted by the grain (columns a table lacks are skipped), a single row group:
# 301 to 407 rows give nothing to prune by row, only by column.
WIDE_ORDER = ("player_id", "team_id", "position_group")
WIDE_ROW_GROUP_ROWS: int | None = None
# Long fact: sorted by metric first, so each row group covers a narrow range of metrics.
FACT_ORDER = ("metric", "sport", "family", "player_id", "team_id", "position_group")
FACT_ROW_GROUP_ROWS = 50_000

COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3
PARQUET_VERSION = "2.6"

_NAMES = "|".join(re.escape(table) for table, _, _ in TABLES)
# What publishing may delete: `<known table>.<8 hex>.parquet`, nothing else.
HASHED_FILE = re.compile(rf"(?:{_NAMES})\.[0-9a-f]{{8}}\.parquet")


@dataclass(frozen=True)
class Built:
    entry: dict[str, Any]
    data: bytes


def warehouse_dir(out_dir: Path) -> Path:
    return out_dir / WAREHOUSE_DIR


def warehouse_path(out_dir: Path) -> Path:
    return out_dir / WAREHOUSE_JSON


def _order_for(table: str, columns: list[str]) -> list[str]:
    wanted = FACT_ORDER if table == FACT else WIDE_ORDER
    return [c for c in wanted if c in columns]


def _row_group_size(table: str, rows: int) -> int:
    size = FACT_ROW_GROUP_ROWS if table == FACT else WIDE_ROW_GROUP_ROWS
    return max(rows, 1) if size is None else size


def _stat(value: Any) -> Any:
    return value if isinstance(value, str | int | float | bool) or value is None else str(value)


def build_table(con: duckdb.DuckDBPyConnection, gold_file: Path, table: str, sport: str) -> Built:
    source = gold_file.as_posix().replace("'", "''")
    columns = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM '{source}'").fetchall()]
    order = _order_for(table, columns)
    ordering = ", ".join(f'"{c}" NULLS LAST' for c in order)
    arrow = con.execute(f"SELECT * FROM '{source}' ORDER BY {ordering}").to_arrow_table()

    sink = io.BytesIO()
    pq.write_table(
        arrow,
        sink,
        compression=COMPRESSION,
        compression_level=COMPRESSION_LEVEL,
        row_group_size=_row_group_size(table, arrow.num_rows),
        version=PARQUET_VERSION,
        use_dictionary=True,
        write_statistics=True,
    )
    data = sink.getvalue()
    sha = hashlib.sha256(data).hexdigest()

    meta = pq.read_metadata(io.BytesIO(data))
    key = meta.schema.names.index(order[0])
    row_groups = []
    for i in range(meta.num_row_groups):
        group = meta.row_group(i)
        stats = group.column(key).statistics
        has = stats is not None and stats.has_min_max
        row_groups.append(
            {
                "rows": group.num_rows,
                "min": _stat(stats.min) if has else None,
                "max": _stat(stats.max) if has else None,
            }
        )
    entry = {
        "table": table,
        "sport": sport,
        "file": f"{table}.{sha[:8]}.parquet",
        "rows": meta.num_rows,
        "columns": meta.num_columns,
        "order_by": order,
        "row_groups": row_groups,
        "bytes": len(data),
        "sha256": sha,
    }
    return Built(entry, data)


def build_all(gold_dir: Path) -> list[Built]:
    con = duckdb.connect()
    built = []
    for table, model, sport in TABLES:
        gold_file = gold_dir / model / "data.parquet"
        if not gold_file.is_file():
            raise FileNotFoundError(f"{gold_file} missing; run `tracklab build` (gold) first")
        built.append(build_table(con, gold_file, table, sport))
    return built


def render(built: list[Built]) -> str:
    payload = {
        "schema_version": 1,
        "writer": {
            "library": "pyarrow",
            "version": pa.__version__,
            "compression": COMPRESSION,
            "compression_level": COMPRESSION_LEVEL,
            "parquet_version": PARQUET_VERSION,
        },
        "tables": [b.entry for b in built],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def stale_files(directory: Path, keep: set[str]) -> list[Path]:
    """Files of an older hash: a known table name, 8 hex digits, `.parquet`, and not in `keep`."""
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file()
        and not p.is_symlink()
        and HASHED_FILE.fullmatch(p.name)
        and p.name not in keep
    )


def check_warehouse(built: list[Built], out_dir: Path) -> list[str]:
    """Differences between what gold would publish now and what is on disk."""
    problems = []
    directory = warehouse_dir(out_dir)
    for b in built:
        path = directory / b.entry["file"]
        if not path.is_file():
            problems.append(f"{path.name} missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != b.entry["sha256"]:
            problems.append(f"{path.name} differs from what gold produces (sha256)")
    manifest = warehouse_path(out_dir)
    if not manifest.is_file():
        problems.append(f"{manifest.name} missing")
    elif manifest.read_text(encoding="utf-8") != render(built):
        problems.append(f"{manifest.name} differs from what gold produces")
    problems.extend(
        f"{p.name} is a stale file"
        for p in stale_files(directory, {b.entry["file"] for b in built})
    )
    return problems


def run_publish_warehouse(data_dir: Path, out_dir: Path, *, check: bool = False) -> int:
    try:
        built = build_all(data_dir / "gold")
    except FileNotFoundError as error:
        print(f"publish warehouse: {error}")
        return 1
    for b in built:
        e = b.entry
        print(
            f"publish warehouse: {e['table']}: {e['rows']} rows, {e['columns']} columns, "
            f"{len(e['row_groups'])} row groups, {e['bytes']} bytes, sha256={e['sha256']}"
        )

    if check:
        problems = check_warehouse(built, out_dir)
        if problems:
            detail = "\n  ".join(problems)
            print(f"publish warehouse --check: {len(problems)} problem(s):\n  {detail}")
            return 1
        print(f"publish warehouse --check: {len(built)} files match gold, sha256 and rows")
        return 0

    directory = warehouse_dir(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    for b in built:
        (directory / b.entry["file"]).write_bytes(b.data)
    # The new manifest goes in before the old files go out: an interruption in between
    # leaves stale files (which `--check` names), never a manifest pointing at deleted ones.
    path = warehouse_path(out_dir)
    pending = path.with_name(path.name + ".tmp")
    pending.write_text(render(built), encoding="utf-8", newline="\n")
    pending.replace(path)
    print(f"publish warehouse: {path} ({path.stat().st_size} bytes)")
    for stale in stale_files(directory, {b.entry["file"] for b in built}):
        stale.unlink()
        print(f"publish warehouse: removed {stale.name}")
    return 0
