"""`freeze_family` on synthetic `dynamic_events.json` data. No real data, no network.

Every test calls `tracklab.formats.basketball.freeze_family` (and `pa_schema`)
directly on rows read back from a JSON file written to `tmp_path`, never
`freeze_basketball` itself, which also needs a manifest and a raw root: that
plumbing belongs to `tests/unit/test_bronze_basketball_events.py`. Each test isolates
one rule from the module's docstring: scalar type inference (`bool` measured before
`int`), a key that is null in one match and has a value in another, a coordinate list
(POINT2D), an id list (LIST<BIGINT>), the `touchWallClock` cast, and the two ways a
family can disagree across matches (a key too many, a key too few) -- plus the two
safety-net failures the real bundle never triggers (an always-null key, an
always-empty list) so they are proven to fail here instead of nowhere.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from tracklab.formats.basketball import (
    FrozenColumn,
    FrozenFamily,
    freeze_family,
    load_family,
    pa_schema,
)

SPORT = "basketball"
SOURCE_ID = "opendata-basketball"
COMMIT = "deadbeef" * 5


def write_family(tmp_path: Path, match_id: int, family: str, rows: list[dict[str, Any]]) -> str:
    """Writes `{"<family>": rows}` as a synthetic `dynamic_events.json`, returns its path."""
    rel = f"data/matches/{match_id}/{match_id}_dynamic_events.json"
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({family: rows}), encoding="utf-8")
    return rel


def read_back(tmp_path: Path, rel: str, family: str) -> list[dict[str, Any]]:
    """Round-trips through the file, like the real freezer does, instead of reusing `rows`."""
    return json.loads((tmp_path / rel).read_text(encoding="utf-8"))[family]


def column(frozen: FrozenFamily, name: str) -> FrozenColumn:
    return next(c for c in frozen.columns if c.name == name)


# --- scalar type inference -----------------------------------------------------------


def test_infers_bool_int_float_str_and_bool_before_int(tmp_path: Path) -> None:
    rows = [
        {"id": "a", "n": 1, "x": 1.5, "flag": True},
        {"id": "b", "n": 2, "x": 2.5, "flag": False},
    ]
    rel = write_family(tmp_path, 900001, "widgets", rows)
    frozen = freeze_family(
        "widgets", [(rel, read_back(tmp_path, rel, "widgets"))], SPORT, SOURCE_ID, COMMIT
    )
    assert column(frozen, "id").type == "VARCHAR"
    assert column(frozen, "n").type == "BIGINT"
    assert column(frozen, "x").type == "DOUBLE"
    assert column(frozen, "flag").type == "BOOLEAN", "bool must not be read as BIGINT"
    assert all(not c.nullable for c in frozen.columns), "nothing was ever null"


def test_pa_schema_prepends_lineage_and_maps_scalars(tmp_path: Path) -> None:
    rows = [{"flag": True, "n": 1, "x": 1.5, "label": "a"}]
    rel = write_family(tmp_path, 900001, "widgets", rows)
    frozen = freeze_family("widgets", [(rel, rows)], SPORT, SOURCE_ID, COMMIT)
    schema = pa_schema(frozen)
    assert schema.names[:4] == ["sport", "match_id", "source_file", "source_row"]
    assert schema.field("flag").type == pa.bool_()
    assert schema.field("n").type == pa.int64()
    assert schema.field("x").type == pa.float64()
    assert schema.field("label").type == pa.string()


# --- a key null in one match, valued in another --------------------------------------


def test_key_null_in_one_match_and_valued_in_another_is_nullable(tmp_path: Path) -> None:
    rel1 = write_family(tmp_path, 900001, "widgets", [{"note": None}])
    rel2 = write_family(tmp_path, 900002, "widgets", [{"note": "hi"}])
    files = [
        (rel1, read_back(tmp_path, rel1, "widgets")),
        (rel2, read_back(tmp_path, rel2, "widgets")),
    ]
    frozen = freeze_family("widgets", files, SPORT, SOURCE_ID, COMMIT)
    note = column(frozen, "note")
    assert note.type == "VARCHAR"
    assert note.nullable is True
    assert frozen.rows_read == 2
    assert frozen.frozen_from == (rel1, rel2)


# --- coordinate list -> POINT2D --------------------------------------------------------


def test_coordinate_list_is_point2d_opened_into_two_double_columns(tmp_path: Path) -> None:
    rows = [{"location": [1.0, 2.0]}, {"location": None}, {"location": [3.5, -4.5]}]
    rel = write_family(tmp_path, 900001, "widgets", rows)
    frozen = freeze_family("widgets", [(rel, rows)], SPORT, SOURCE_ID, COMMIT)
    location = column(frozen, "location")
    assert location.type == "POINT2D"
    assert location.nullable is True

    schema = pa_schema(frozen)
    assert "location" not in schema.names
    assert schema.field("location_x").type == pa.float64()
    assert schema.field("location_y").type == pa.float64()
    assert schema.field("location_x").nullable is True
    assert schema.field("location_y").nullable is True


def test_float_list_not_always_length_2_is_rejected(tmp_path: Path) -> None:
    rows = [{"location": [1.0, 2.0]}, {"location": [1.0, 2.0, 3.0]}]
    rel = write_family(tmp_path, 900001, "widgets", rows)
    with pytest.raises(ValueError, match=r"POINT2D needs 2"):
        freeze_family("widgets", [(rel, rows)], SPORT, SOURCE_ID, COMMIT)


# --- id list -> LIST<BIGINT> -----------------------------------------------------------


def test_id_list_is_list_bigint(tmp_path: Path) -> None:
    rows = [{"offPlayerIds": []}, {"offPlayerIds": [1, 2, 3, 4, 5]}]
    rel = write_family(tmp_path, 900001, "widgets", rows)
    frozen = freeze_family("widgets", [(rel, rows)], SPORT, SOURCE_ID, COMMIT)
    ids = column(frozen, "offPlayerIds")
    assert ids.type == "LIST<BIGINT>"
    assert ids.nullable is False, "the key itself is never null, only sometimes empty"

    schema = pa_schema(frozen)
    assert schema.field("offPlayerIds").type == pa.list_(pa.int64())


def test_string_list_is_list_varchar(tmp_path: Path) -> None:
    rows = [{"outcomes": []}, {"outcomes": ["made", "assisted"]}]
    rel = write_family(tmp_path, 900001, "widgets", rows)
    frozen = freeze_family("widgets", [(rel, rows)], SPORT, SOURCE_ID, COMMIT)
    assert column(frozen, "outcomes").type == "LIST<VARCHAR>"


# --- the touchWallClock cast -----------------------------------------------------------


def test_touch_wall_clock_cast_is_declared_and_round_trips(tmp_path: Path) -> None:
    rows = [{"touchWallClock": "53080"}, {"touchWallClock": None}, {"touchWallClock": "77000"}]
    rel = write_family(tmp_path, 900001, "closeouts", rows)
    frozen = freeze_family("closeouts", [(rel, rows)], SPORT, SOURCE_ID, COMMIT)
    touch = column(frozen, "touchWallClock")
    assert touch.type == "BIGINT"
    assert touch.source_type == "VARCHAR"
    assert touch.nullable is True

    schema_path = tmp_path / "events_closeouts.schema.json"
    schema_path.write_text(frozen.to_json(), encoding="utf-8")
    reloaded = load_family(schema_path)
    assert reloaded == frozen, "to_json/load_family round-trips exactly"
    assert '"source_type": "VARCHAR"' in schema_path.read_text(encoding="utf-8")


def test_touch_wall_clock_cast_fails_on_a_value_that_does_not_parse(tmp_path: Path) -> None:
    rows = [{"touchWallClock": "not-a-number"}]
    rel = write_family(tmp_path, 900001, "closeouts", rows)
    with pytest.raises(ValueError, match="does not cast to BIGINT"):
        freeze_family("closeouts", [(rel, rows)], SPORT, SOURCE_ID, COMMIT)


# --- a key too many or too few across matches fails, naming it ------------------------


def test_extra_key_in_one_match_fails_naming_it(tmp_path: Path) -> None:
    rows1 = [{"id": 1, "n": 10}]
    rows2 = [{"id": 2, "n": 20, "surprise": True}]
    rel1 = write_family(tmp_path, 900001, "widgets", rows1)
    rel2 = write_family(tmp_path, 900002, "widgets", rows2)
    files = [(rel1, rows1), (rel2, rows2)]
    with pytest.raises(ValueError, match=r"extra \['surprise'\]"):
        freeze_family("widgets", files, SPORT, SOURCE_ID, COMMIT)


def test_missing_key_in_one_match_fails_naming_it(tmp_path: Path) -> None:
    rows1 = [{"id": 1, "n": 10}]
    rows2 = [{"id": 2}]
    rel1 = write_family(tmp_path, 900001, "widgets", rows1)
    rel2 = write_family(tmp_path, 900002, "widgets", rows2)
    files = [(rel1, rows1), (rel2, rows2)]
    with pytest.raises(ValueError, match=r"missing \['n'\]"):
        freeze_family("widgets", files, SPORT, SOURCE_ID, COMMIT)


# --- the two safety nets the real bundle never triggers --------------------------------


def test_always_null_key_fails_naming_it(tmp_path: Path) -> None:
    rows = [{"id": 1, "ghost": None}, {"id": 2, "ghost": None}]
    rel = write_family(tmp_path, 900001, "widgets", rows)
    with pytest.raises(ValueError, match=r"widgets\.ghost: always null"):
        freeze_family("widgets", [(rel, rows)], SPORT, SOURCE_ID, COMMIT)


def test_always_empty_list_fails_naming_it(tmp_path: Path) -> None:
    rows = [{"ids": []}, {"ids": []}]
    rel = write_family(tmp_path, 900001, "widgets", rows)
    with pytest.raises(ValueError, match=r"widgets\.ids: list is always empty"):
        freeze_family("widgets", [(rel, rows)], SPORT, SOURCE_ID, COMMIT)


def test_two_distinct_non_null_types_fails_naming_it(tmp_path: Path) -> None:
    rows = [{"mixed": 1}, {"mixed": "one"}]
    rel = write_family(tmp_path, 900001, "widgets", rows)
    with pytest.raises(ValueError, match=r"widgets\.mixed: distinct non-null types"):
        freeze_family("widgets", [(rel, rows)], SPORT, SOURCE_ID, COMMIT)
