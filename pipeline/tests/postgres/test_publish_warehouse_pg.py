"""`tracklab publish warehouse-pg` (task 44) against a live Postgres: the example queries, run on
the dimensional model by the read-only role, answer what `warehouse_examples.json` says (computed
from the wide gold tables in plain Python), and the snapshot names no host, user or database.
"""

from __future__ import annotations

import json
import secrets
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tracklab.cli import main
from tracklab.load.postgres import READER_ROLE, TABLES, connect, set_reader_password
from tracklab.paths import data_root
from tracklab.publish.examples import EXAMPLES_JSON
from tracklab.publish.warehouse_pg import WAREHOUSE_PG_JSON, WHERE, render_examples, run_example

WEB_DATA = Path(__file__).resolve().parents[3] / "web" / "public" / "data"
Answer = Callable[[dict[str, Any], list[str], list[list[Any]]], None]


def _publish(dsn: str, data_dir: Path, out_dir: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    shutil.copy(WEB_DATA / EXAMPLES_JSON, out_dir / EXAMPLES_JSON)
    monkeypatch.setenv("TRACKLAB_TEST_PUBLISH_DSN", dsn)
    return main(
        [
            "publish",
            "warehouse-pg",
            "--dsn-env",
            "TRACKLAB_TEST_PUBLISH_DSN",
            "--where",
            "ci",
            "--data-dir",
            str(data_dir),
            "--out-dir",
            str(out_dir),
        ]
    )


def test_the_reader_answers_the_examples_like_the_examples_file(
    loaded_dsn: str, examples_file: dict[str, Any], assert_same_answer: Answer
) -> None:
    password = secrets.token_urlsafe(24)
    with connect(loaded_dsn) as conn:
        set_reader_password(conn, password)
    reader = make_conninfo(loaded_dsn, user=READER_ROLE, password=password)
    with psycopg.connect(reader, autocommit=True) as r:
        queries = render_examples(r, examples_file)
        for example in examples_file["examples"]:
            got = run_example(r, example["id"], queries[example["id"]])
            assert_same_answer(example, got["columns"], got["rows"])


def test_publish_writes_what_postgres_answers_and_names_no_host(
    loaded_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    examples_file: dict[str, Any],
    assert_same_answer: Answer,
    assert_no_local_traces: Callable[[object], None],
) -> None:
    assert _publish(loaded_dsn, data_root(), tmp_path, monkeypatch) == 0
    text = (tmp_path / WAREHOUSE_PG_JSON).read_text(encoding="utf-8")
    payload = json.loads(text)
    with connect(loaded_dsn) as conn:
        version = conn.execute("SHOW server_version").fetchone()
    assert version is not None
    assert payload["source"] == {
        "engine": "PostgreSQL",
        "version": version[0].split()[0],
        "where": WHERE["ci"],
        "where_id": "ci",
        "block_size": 8192,
    }
    with duckdb.connect() as con:
        gold = {
            t.name: con.execute(
                "SELECT count(*) FROM read_parquet(?)",
                [(data_root() / "gold" / t.gold / "data.parquet").as_posix()],
            ).fetchall()[0][0]
            for t in TABLES
        }
    assert {t["table"]: t["rows"] for t in payload["tables"]} == gold
    assert [e["id"] for e in payload["examples"]] == [e["id"] for e in examples_file["examples"]]
    for want, got in zip(examples_file["examples"], payload["examples"], strict=True):
        assert_same_answer(want, got["columns"], got["rows"])
        assert got["plan"][0]["Execution Time"] == got["execution_ms"]
    assert_no_local_traces(payload)
    info = conninfo_to_dict(loaded_dsn)
    for part in ("host", "dbname", "password"):
        if info.get(part):
            assert str(info[part]) not in text


def test_publish_refuses_a_postgres_that_does_not_hold_gold(
    loaded_dsn: str, tmp_gold: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    teams = tmp_gold / "gold" / "dim_season_team" / "data.parquet"
    with duckdb.connect() as con:
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{teams.as_posix()}') LIMIT 1) "
            f"TO '{(tmp_path / 'one.parquet').as_posix()}' (FORMAT parquet)"
        )
    (tmp_path / "one.parquet").replace(teams)
    out = tmp_path / "out"
    out.mkdir()
    assert _publish(loaded_dsn, tmp_gold, out, monkeypatch) == 1
    assert not (out / WAREHOUSE_PG_JSON).exists()
