"""The versioned `web/public/data/warehouse_pg.json` (task 44), without a database: every example
has its Postgres query, the snapshot answers what `warehouse_examples.json` says, and it says
which Postgres measured it without naming the machine.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import pytest

from tracklab.load.postgres import TABLES
from tracklab.paths import data_root
from tracklab.publish.warehouse_pg import EXAMPLES_DIR, WAREHOUSE_PG_JSON, WHERE, render_examples

WEB_DATA = Path(__file__).resolve().parents[3] / "web" / "public" / "data"


def _snapshot() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((WEB_DATA / WAREHOUSE_PG_JSON).read_text(encoding="utf-8"))
    return data


def test_every_example_has_one_postgres_query(examples_file: dict[str, Any]) -> None:
    assert sorted(p.stem for p in EXAMPLES_DIR.glob("*.sql")) == sorted(
        e["id"] for e in examples_file["examples"]
    )


def test_the_snapshot_answers_like_the_examples_file(
    examples_file: dict[str, Any],
    assert_same_answer: Callable[[dict[str, Any], list[str], list[list[Any]]], None],
) -> None:
    snapshot = _snapshot()
    assert [e["id"] for e in snapshot["examples"]] == [e["id"] for e in examples_file["examples"]]
    for want, got in zip(examples_file["examples"], snapshot["examples"], strict=True):
        assert_same_answer(want, got["columns"], got["rows"])


def test_the_snapshot_says_which_postgres_and_names_no_machine(
    assert_no_local_traces: Callable[[object], None],
) -> None:
    snapshot = _snapshot()
    source = snapshot["source"]
    assert source["engine"] == "PostgreSQL"
    assert source["where"] == WHERE[source["where_id"]]
    assert [t["table"] for t in snapshot["tables"]] == [t.name for t in TABLES]
    assert_no_local_traces(snapshot)


def test_the_snapshot_holds_the_sql_of_the_example_files(examples_file: dict[str, Any]) -> None:
    """The route runs `examples[].sql` of this JSON. A `.sql` edited without publishing again
    would leave it running the old query, and if the answers did not change no other test would
    see it (review V of P4, B3)."""
    published = {e["id"]: e["sql"] for e in _snapshot()["examples"]}
    assert published == render_examples(None, examples_file)


def test_the_snapshot_tables_have_the_rows_of_gold() -> None:
    """`tables[].rows` against a `count(*)` of each gold table, by DuckDB and not by Postgres."""
    files = {t.name: data_root() / "gold" / t.gold / "data.parquet" for t in TABLES}
    if not all(f.is_file() for f in files.values()):
        pytest.skip("needs the four gold tables")
    with duckdb.connect() as con:
        gold = {
            name: con.execute("SELECT count(*) FROM read_parquet(?)", [f.as_posix()]).fetchall()[0][
                0
            ]
            for name, f in files.items()
        }
    assert {t["table"]: t["rows"] for t in _snapshot()["tables"]} == gold
