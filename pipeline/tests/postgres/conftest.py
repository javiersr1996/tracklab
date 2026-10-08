"""Postgres for the tests of task 44. `$TRACKLAB_TEST_PG_DSN` names a server and a role that may
create databases (a local Docker `postgres:17.11`, or the service container of `ci.yml`); every
test that asks for one gets a throwaway database, dropped afterwards. Without the variable those
tests skip, unless `$TRACKLAB_REQUIRE_PG` is set, as in CI, where they fail instead: a test that
skips in the only place it runs protects nothing.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from tracklab.load.postgres import TABLES, connect, load, migrate
from tracklab.paths import data_root

PG_ENV = "TRACKLAB_TEST_PG_DSN"
REQUIRE_ENV = "TRACKLAB_REQUIRE_PG"
WEB_DATA = Path(__file__).resolve().parents[3] / "web" / "public" / "data"


def gold_built(root: Path) -> bool:
    return all((root / "gold" / t.gold / "data.parquet").is_file() for t in TABLES)


@pytest.fixture(scope="session")
def pg_admin_dsn() -> str:
    dsn = os.environ.get(PG_ENV)
    if not dsn:
        if os.environ.get(REQUIRE_ENV):
            pytest.fail(f"${REQUIRE_ENV} is set and ${PG_ENV} is not")
        pytest.skip(f"needs ${PG_ENV}")
    return dsn


@contextmanager
def throwaway_database(admin_dsn: str, owner: str | None = None) -> Iterator[str]:
    name = f"tracklab_test_{secrets.token_hex(4)}"
    create = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
    if owner is not None:
        create = sql.SQL("{} OWNER {}").format(create, sql.Identifier(owner))
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(create)
    try:
        yield make_conninfo(admin_dsn, dbname=name)
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def pg_dsn(pg_admin_dsn: str) -> Iterator[str]:
    """An empty database."""
    with throwaway_database(pg_admin_dsn) as dsn:
        yield dsn


@pytest.fixture
def owned_dsn(pg_admin_dsn: str) -> Iterator[tuple[str, str]]:
    """An empty database owned by a new role that is not a superuser, as the owner is on Neon:
    `(dsn as the admin, dsn as the owner)`. The role goes with the database."""
    owner, password = f"tracklab_test_owner_{secrets.token_hex(4)}", secrets.token_urlsafe(24)
    with psycopg.connect(pg_admin_dsn, autocommit=True) as conn:
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(owner), sql.Literal(password)
            )
        )
    try:
        with throwaway_database(pg_admin_dsn, owner=owner) as dsn:
            yield dsn, make_conninfo(dsn, user=owner, password=password)
    finally:
        with psycopg.connect(pg_admin_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(owner)))


@pytest.fixture(scope="module")
def loaded_dsn(pg_admin_dsn: str) -> Iterator[str]:
    """A database with the schema applied and gold loaded once, shared by a module's tests."""
    if not gold_built(data_root()):
        pytest.skip("needs the four gold tables")
    with throwaway_database(pg_admin_dsn) as dsn:
        with connect(dsn) as conn:
            migrate(conn)
            load(conn, data_root())
        yield dsn


@pytest.fixture
def tmp_gold(tmp_path: Path) -> Path:
    """A data root with a copy of the four gold tables, free to rewrite."""
    if not gold_built(data_root()):
        pytest.skip("needs the four gold tables")
    for t in TABLES:
        target = tmp_path / "gold" / t.gold
        target.mkdir(parents=True)
        shutil.copy(data_root() / "gold" / t.gold / "data.parquet", target / "data.parquet")
    return tmp_path


@pytest.fixture(scope="session")
def examples_file() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (WEB_DATA / "warehouse_examples.json").read_text(encoding="utf-8")
    )
    return data


def same_answer(expected: dict[str, Any], columns: list[str], rows: list[list[Any]]) -> list[str]:
    """Where an answer differs from `warehouse_examples.json`: column names, row count, and each
    cell (numbers the query rounds within half a unit of its last digit, the rest exactly)."""
    wanted = [c["name"] for c in expected["columns"]]
    if columns != wanted:
        return [f"columns {columns} != {wanted}"]
    if len(rows) != len(expected["rows"]):
        return [f"{len(rows)} rows != {len(expected['rows'])}"]
    problems = []
    for i, (got, want) in enumerate(zip(rows, expected["rows"], strict=True)):
        for column, g, w in zip(expected["columns"], got, want, strict=True):
            digits = column["decimals"]
            close = abs(g - w) <= 0.5 * 10**-digits + 1e-9 if digits is not None else g == w
            if not close:
                problems.append(f"{expected['id']} row {i} {column['name']}: {g!r} != {w!r}")
    return problems


@pytest.fixture
def assert_same_answer() -> Callable[[dict[str, Any], list[str], list[list[Any]]], None]:
    def check(expected: dict[str, Any], columns: list[str], rows: list[list[Any]]) -> None:
        assert same_answer(expected, columns, rows) == []

    return check
