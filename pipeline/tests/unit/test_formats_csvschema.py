"""`formats/csvschema.py`: the DATE gap task 8 found in `pa_schema` and fixed there.

Basketball's 3 season aggregates (BIGINT/DOUBLE/VARCHAR only) were the only CSV
families that had ever gone through `pa_schema` before task 8's football aggregates
added `player_birthdate` (sniffed by DuckDB as DATE): `_PA_TYPES` had no entry for
it, so `pa_schema` raised a bare `KeyError('DATE')`. Fixed with one entry
(`pa.date32()`) plus a named error for the next unknown type, covered here so the
next TIMESTAMP or similar a future `freeze-schema` run congeals gets caught by a
test instead of a half-built Parquet schema.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tracklab.formats.csvschema import (
    Column,
    FrozenSchema,
    freeze_csv_family,
    load_schema,
    pa_schema,
    read_typed,
)

PIPELINE = Path(__file__).resolve().parents[2]
SCHEMAS_ROOT = PIPELINE / "src" / "tracklab" / "bronze" / "schemas"


def _owned_schema_paths() -> list[Path]:
    """`*.schema.json` under `bronze/schemas/` that this module's own freezer
    produced, identified by the `header_sha256` key `freeze_csv_family` always
    writes (never a hand-picked filename list, so a new CSV family is picked up
    automatically). Basketball's 20 event families are frozen by
    `formats.basketball` instead (POINT2D/LIST types, no `header_sha256`) and are
    out of scope for this module: `csvschema.load_schema` cannot even parse their
    JSON shape (`KeyError: 'header_sha256'`), a different failure than the type gap
    this test guards.
    """
    paths = sorted(SCHEMAS_ROOT.glob("**/*.schema.json"))
    return [p for p in paths if "header_sha256" in json.loads(p.read_text(encoding="utf-8"))]


def test_owned_schema_count_is_the_full_csv_frozen_vocabulary() -> None:
    """Guards the glob itself: dynamic_events, phases_of_play and the 3+3 season
    aggregates of both sports. If a 9th CSV family is ever frozen through this
    module, this must grow on purpose, not silently."""
    paths = _owned_schema_paths()
    print("\n" + "\n".join(p.relative_to(SCHEMAS_ROOT).as_posix() for p in paths))
    assert len(paths) == 8, f"expected 8 csvschema-owned schemas, found {len(paths)}"


@pytest.mark.parametrize("path", _owned_schema_paths(), ids=lambda p: p.name)
def test_pa_schema_builds_every_frozen_csv_schema(path: Path) -> None:
    """The entire real type vocabulary this module owns: BOOLEAN, BIGINT, DOUBLE,
    VARCHAR and now DATE (`player_birthdate`, the 3 football season aggregates)."""
    frozen = load_schema(path)
    schema = pa_schema(frozen)
    types = sorted({str(f.type) for f in schema})
    print(f"{path.name}: {len(schema)} columns, types={types}")
    assert len(schema) == len(frozen.columns)


def test_date_round_trips_through_read_typed_pa_schema_and_parquet(tmp_path: Path) -> None:
    """`read_typed` (DuckDB) -> `pa_schema` (cast) -> Parquet -> read back: the same
    `player_birthdate` the raw CSV declared must come back unchanged."""
    con = duckdb.connect()
    path = tmp_path / "aggregates_physical.csv"
    raw_birthdate = "1993-06-02"
    path.write_text(
        f"player_id,player_birthdate,minutes\n1,{raw_birthdate},812.5\n2,1998-11-20,640.0\n",
        encoding="utf-8",
    )
    frozen = freeze_csv_family("aggregates_physical", [path], tmp_path, con)
    types = {c.name: c.type for c in frozen.columns}
    assert types["player_birthdate"] == "DATE"

    data = read_typed(frozen, path, con)
    schema = pa_schema(frozen)
    table = pa.Table.from_arrays([data.column(f.name).cast(f.type) for f in schema], schema=schema)

    out_path = tmp_path / "out.parquet"
    pq.write_table(table, out_path)
    written_birthdate = pq.read_table(out_path).column("player_birthdate")[0].as_py()

    print(f"raw csv player_birthdate={raw_birthdate} parquet player_birthdate={written_birthdate}")
    assert written_birthdate == datetime.date(1993, 6, 2)
    assert str(written_birthdate) == raw_birthdate


def test_pa_schema_names_the_unknown_type() -> None:
    """An unknown frozen type must name the table, the column and the type, not a
    bare `KeyError` that sends the caller hunting through the schema file."""
    schema = FrozenSchema(
        table="mystery",
        header_sha256="0" * 64,
        columns=(Column("player_id", "BIGINT"), Column("event_ts", "TIMESTAMP")),
        all_null_columns=(),
        frozen_from=("some/file.csv",),
    )
    with pytest.raises(ValueError, match=r"mystery\.event_ts: no pyarrow type for 'TIMESTAMP'"):
        pa_schema(schema)
