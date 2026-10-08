"""`tracklab publish warehouse-pg`: what Postgres answers to the `/warehouse` examples, and how
(task 44, P4).

The five example queries of the page, rewritten for the dimensional model in
`pipeline/sql/examples/<id>.sql` with the players and thresholds of `warehouse_examples.json`,
run against the Postgres that `tracklab load postgres` filled, in a read-only transaction: first
under `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, then once more for their rows. The result is
`web/public/data/warehouse_pg.json`: per query the SQL as run, its columns, rows and plan; per
table its rows and bytes; and where the numbers come from (engine, version and a fixed sentence
for local, CI or Neon). No host, user, database name or path: the connection string stays in its
environment variable. Timings are measured, not reproducible, so there is no `--check`: the tests
compare the rows with `warehouse_examples.json`, which another engine computed from another model.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import psycopg
from psycopg import sql

from tracklab.load.postgres import (
    SCHEMA,
    SQL_DIR,
    TABLES,
    Connection,
    LoadError,
    Table,
    connect,
    env_value,
    gold_file,
)
from tracklab.publish.examples import EXAMPLES_JSON

WAREHOUSE_PG_JSON = "warehouse_pg.json"
EXAMPLES_DIR = SQL_DIR / "examples"

# What the JSON says about the database it measured, in words fixed here: never its address.
WHERE = {
    "local": "a local Postgres in Docker, not Neon: the Neon project does not exist yet",
    "ci": "the Postgres service container of CI, not Neon: the Neon project does not exist yet",
    "neon": "Neon, free plan",
}


def render_examples(
    conn: Connection, examples: dict[str, Any], examples_dir: Path = EXAMPLES_DIR
) -> dict[str, str]:
    """The SQL of each example id, with the parameters of `warehouse_examples.json` as literals."""
    ids = [e["id"] for e in examples["examples"]]
    files = {p.stem: p for p in examples_dir.glob("*.sql")}
    if sorted(files) != sorted(ids):
        raise LoadError(f"example ids {sorted(ids)} and SQL files {sorted(files)} differ")
    params = examples["params"]
    args: dict[str, sql.Composable] = {k: sql.Literal(v) for k, v in params.items()}
    args["football_metric_column"] = sql.Identifier(params["football_metric"])
    return {
        i: sql.SQL(files[i].read_text(encoding="utf-8")).format(**args).as_string(conn) for i in ids
    }


def _cell(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


def run_example(conn: Connection, example_id: str, query: str) -> dict[str, Any]:
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        row = conn.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}").fetchone()
        assert row is not None
        explain = row[0]
        cursor = conn.execute(query)
        assert cursor.description is not None
        columns = [d.name for d in cursor.description]
        rows = [[_cell(v) for v in r] for r in cursor.fetchall()]
    top = explain[0]
    nodes = list(_nodes(top["Plan"]))
    return {
        "id": example_id,
        "sql": query,
        "columns": columns,
        "rows": rows,
        "execution_ms": top["Execution Time"],
        "planning_ms": top["Planning Time"],
        "shared_hit_blocks": top["Plan"]["Shared Hit Blocks"],
        "shared_read_blocks": top["Plan"]["Shared Read Blocks"],
        "indexes": sorted({n["Index Name"] for n in nodes if "Index Name" in n}),
        "seq_scans": sorted({n["Relation Name"] for n in nodes if n["Node Type"] == "Seq Scan"}),
        "plan": explain,
    }


def _gold_count(data_dir: Path, table: Table) -> int:
    with duckdb.connect() as con:
        row = con.execute(
            "SELECT count(*) FROM read_parquet(?)", [gold_file(data_dir, table).as_posix()]
        ).fetchone()
    assert row is not None
    return int(row[0])


def table_sizes(conn: Connection, data_dir: Path) -> list[dict[str, Any]]:
    """Rows and bytes of each table; refuses if Postgres does not hold what gold holds."""
    out = []
    for t in TABLES:
        name = f"{SCHEMA}.{t.name}"
        row = conn.execute(
            sql.SQL(
                "SELECT (SELECT count(*) FROM {}), pg_relation_size(%(t)s::regclass), "
                "pg_indexes_size(%(t)s::regclass), pg_total_relation_size(%(t)s::regclass)"
            ).format(sql.Identifier(SCHEMA, t.name)),
            {"t": name},
        ).fetchone()
        assert row is not None
        rows, table_bytes, index_bytes, total_bytes = row
        if rows != _gold_count(data_dir, t):
            raise LoadError(f"{name} has {rows} rows and gold does not: run tracklab load postgres")
        out.append(
            {
                "table": t.name,
                "rows": rows,
                "table_bytes": table_bytes,
                "index_bytes": index_bytes,
                "total_bytes": total_bytes,
            }
        )
    return out


def build(conn: Connection, data_dir: Path, examples: dict[str, Any], where: str) -> dict[str, Any]:
    version = conn.execute("SHOW server_version").fetchone()
    block = conn.execute("SHOW block_size").fetchone()
    database = conn.execute("SELECT pg_database_size(current_database())").fetchone()
    assert version is not None and block is not None and database is not None
    tables = table_sizes(conn, data_dir)
    queries = render_examples(conn, examples)
    return {
        "schema_version": 1,
        "measured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "engine": "PostgreSQL",
            "version": str(version[0]).split()[0],
            "where": WHERE[where],
            "where_id": where,
            "block_size": int(block[0]),
        },
        "database_bytes": database[0],
        "tables": tables,
        "examples": [run_example(conn, i, q) for i, q in queries.items()],
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def run_publish_warehouse_pg(data_dir: Path, out_dir: Path, dsn_env: str, where: str) -> int:
    try:
        examples = json.loads((out_dir / EXAMPLES_JSON).read_text(encoding="utf-8"))
        with connect(env_value(dsn_env)) as conn:
            text = render(build(conn, data_dir, examples, where))
    except (LoadError, psycopg.Error, FileNotFoundError) as error:
        print(f"publish warehouse-pg: {error}")
        return 1
    path = out_dir / WAREHOUSE_PG_JSON
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"publish warehouse-pg: {path} ({path.stat().st_size} bytes)")
    return 0
