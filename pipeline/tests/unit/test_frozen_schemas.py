"""Every frozen schema on disk must translate to pyarrow, whatever types it carries.

`formats.csvschema.pa_schema` mapped four DuckDB types until task 8 built football's
season aggregates and hit `player_birthdate`, a DATE. The type had been frozen by task
4 long before; nothing was wrong with it. The gap was that the only schemas that had
ever gone through `pa_schema` were basketball's 3 aggregates, which are BOOLEAN,
BIGINT, DOUBLE and VARCHAR only, so no test could have caught it.

This module closes that by iterating the schema files that exist rather than a list
written by hand: a type frozen tomorrow fails here, with the file that carries it,
instead of half-way through a build.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracklab.formats.basketball import load_family
from tracklab.formats.basketball import pa_schema as family_pa_schema
from tracklab.formats.csvschema import Column, FrozenSchema, load_schema
from tracklab.formats.csvschema import pa_schema as csv_pa_schema

SCHEMAS = Path(__file__).resolve().parents[1].parent / "src" / "tracklab" / "bronze" / "schemas"
FROZEN = sorted(SCHEMAS.glob("*/*.schema.json"))


def test_the_schemas_directory_is_not_empty() -> None:
    """Without this, every parametrised test below would vacuously pass."""
    print(f"\n{len(FROZEN)} frozen schemas under {SCHEMAS}")
    assert len(FROZEN) >= 23


@pytest.mark.parametrize("path", FROZEN, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_every_frozen_schema_translates_to_pyarrow(path: Path) -> None:
    """A JSON event family goes through `formats.basketball.pa_schema` (it knows
    POINT2D and the lists), a CSV family through `formats.csvschema.pa_schema`. Both
    mappings are exercised by whichever files are on disk."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "family" in raw:
        schema = family_pa_schema(load_family(path))
    else:
        schema = csv_pa_schema(load_schema(path))
    types = sorted({str(f.type) for f in schema})
    print(f"{path.parent.name}/{path.stem}: {len(schema)} columns, types {types}")
    assert len(schema) > 0


def test_an_unknown_frozen_type_names_the_table_the_column_and_the_type() -> None:
    schema = FrozenSchema(
        table="aggregates_invented",
        header_sha256="00" * 32,
        columns=(Column("player_id", "BIGINT"), Column("signed_at", "TIMESTAMP")),
        all_null_columns=(),
        frozen_from=("data/aggregates/invented.csv",),
    )
    with pytest.raises(ValueError, match=r"aggregates_invented\.signed_at: no pyarrow type"):
        csv_pa_schema(schema)
