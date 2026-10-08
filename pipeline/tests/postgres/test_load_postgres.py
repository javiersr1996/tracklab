"""`tracklab load postgres` (task 44): the incremental load writes only what changed, the schema is
applied once, and the read-only role can only read. The loader's counts are checked against
Postgres by another path: `xmin`, the id of the transaction that wrote each row version, which any
write of a row changes, even one that leaves the same values.
"""

from __future__ import annotations

import secrets
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import psycopg
import pytest
from psycopg import errors, sql
from psycopg.conninfo import make_conninfo

from tracklab.cli import main
from tracklab.load.postgres import (
    READER_ROLE,
    SQL_DIR,
    TABLES,
    Connection,
    LoadError,
    Table,
    connect,
    load,
    migrate,
    row_hash,
    run_load_postgres,
    set_reader_password,
)

FACT = TABLES[-1]
DIM_PLAYER = TABLES[0]


def _gold_rows(root: Path) -> dict[str, int]:
    with duckdb.connect() as con:
        return {
            t.name: con.execute(
                "SELECT count(*) FROM read_parquet(?)",
                [(root / "gold" / t.gold / "data.parquet").as_posix()],
            ).fetchall()[0][0]
            for t in TABLES
        }


def _xmins(conn: Connection, table: Table) -> dict[tuple[Any, ...], str]:
    query = sql.SQL("SELECT {}, xmin::text FROM {}").format(
        sql.SQL(", ").join(map(sql.Identifier, table.key)), sql.Identifier("warehouse", table.name)
    )
    return {tuple(r[:-1]): r[-1] for r in conn.execute(query)}


def _written(before: dict[tuple[Any, ...], str], after: dict[tuple[Any, ...], str]) -> set[Any]:
    """Keys whose row was written between the two snapshots: a new xmin, or a new key."""
    return {k for k, x in after.items() if before.get(k) != x}


def _rewrite(root: Path, model: str, select: str) -> None:
    """Replace a gold table of the copy in `root` with `select` over it (`{src}` is the table)."""
    path = root / "gold" / model / "data.parquet"
    new = path.with_name("new.parquet")
    query = select.format(src=f"read_parquet('{path.as_posix()}')")
    with duckdb.connect() as con:
        con.execute(f"COPY ({query}) TO '{new.as_posix()}' (FORMAT parquet)")
    new.replace(path)


def _counts(rows: list[Any]) -> list[tuple[Any, ...]]:
    return [(c.table, c.inserted, c.updated, c.deleted, c.unchanged) for c in rows]


def test_row_hash_is_stable_and_changes_with_any_column() -> None:
    row = ("basketball", "shots", "attempts", 7, None, None, True, 2.5)
    assert len(row_hash(row)) == 16
    assert row_hash(row) == row_hash(list(row))
    variants = [
        ("basketball", "shots", "attempts", 7, None, None, True, 2.6),
        ("basketball", "shots", "attempts", 7, 0, None, True, 2.5),
        ("basketball", "shots", "attempts", 7, None, "", True, 2.5),
        ("basketball", "shots", "attempts", 7, None, None, False, 2.5),
        ("basketball", "shots", "attempts", 8, None, None, True, 2.5),
    ]
    assert len({row_hash(row), *map(row_hash, variants)}) == 1 + len(variants)
    assert row_hash(("football", 1, date(2001, 2, 3))) != row_hash(("football", 1, None))


def test_a_missing_variable_is_named_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("TRACKLAB_TEST_NOT_SET", raising=False)
    assert run_load_postgres(Path("nowhere"), "TRACKLAB_TEST_NOT_SET") == 1
    assert capsys.readouterr().out == "load postgres: $TRACKLAB_TEST_NOT_SET is not set\n"


def test_migrations_apply_once_and_refuse_a_changed_file(pg_dsn: str, tmp_path: Path) -> None:
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    for path in SQL_DIR.glob("[0-9][0-9][0-9]_*.sql"):
        shutil.copy(path, sql_dir)
    with connect(pg_dsn) as conn:
        assert migrate(conn, sql_dir) == ["001_warehouse", "002_no_temporary_tables"]
        assert migrate(conn, sql_dir) == []
        edited = sql_dir / "001_warehouse.sql"
        edited.write_bytes(edited.read_bytes() + b"-- edited\n")
        with pytest.raises(LoadError, match="changed after it was applied"):
            migrate(conn, sql_dir)


def test_a_second_load_of_the_same_gold_writes_no_row(
    pg_dsn: str, tmp_gold: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gold = _gold_rows(tmp_gold)
    with connect(pg_dsn) as conn:
        migrate(conn)
        first = load(conn, tmp_gold)
        before = {t.name: _xmins(conn, t) for t in TABLES}
    assert _counts(first) == [(t.name, gold[t.name], 0, 0, 0) for t in TABLES]
    assert {name: len(rows) for name, rows in before.items()} == gold

    # The second load goes through the command line, as it would run by hand.
    monkeypatch.setenv("TRACKLAB_TEST_LOAD_DSN", pg_dsn)
    capsys.readouterr()
    argv = ["load", "postgres", "--dsn-env", "TRACKLAB_TEST_LOAD_DSN", "--data-dir", str(tmp_gold)]
    assert main(argv) == 0
    out = capsys.readouterr().out
    for t in TABLES:
        assert f"{t.name} inserted=0 updated=0 deleted=0 unchanged={gold[t.name]}\n" in out
    assert pg_dsn not in out

    with connect(pg_dsn) as conn:
        after = {t.name: _xmins(conn, t) for t in TABLES}
        logged = conn.execute(
            "SELECT table_name, inserted, updated, deleted, unchanged FROM warehouse.load_log "
            "WHERE loaded_at = (SELECT max(loaded_at) FROM warehouse.load_log)"
        ).fetchall()
    assert {name: _written(before[name], after[name]) for name in gold} == {n: set() for n in gold}
    assert sorted(logged) == sorted((t.name, 0, 0, 0, gold[t.name]) for t in TABLES)


def test_a_changed_value_is_one_updated_row(pg_dsn: str, tmp_gold: Path) -> None:
    gold = _gold_rows(tmp_gold)
    # A season-total row of basketball: NULL team and position, so the key match has to treat
    # NULL as a value, or the change would come out as one row deleted and one inserted.
    with duckdb.connect() as con:
        family, metric, player_id, value = con.execute(
            "SELECT family, metric, player_id, value FROM read_parquet(?) WHERE is_season_total "
            "ORDER BY family, metric, player_id LIMIT 1",
            [(tmp_gold / "gold" / FACT.gold / "data.parquet").as_posix()],
        ).fetchall()[0]
    with connect(pg_dsn) as conn:
        migrate(conn)
        load(conn, tmp_gold)
        before = _xmins(conn, FACT)
        _rewrite(
            tmp_gold,
            FACT.gold,
            "SELECT * REPLACE (CASE WHEN is_season_total AND family = '"
            + family
            + "' AND metric = '"
            + metric
            + f"' AND player_id = {player_id} THEN value + 1 ELSE value END AS value) FROM {{src}}",
        )
        counts = load(conn, tmp_gold)
        after = _xmins(conn, FACT)
        stored = conn.execute(
            "SELECT value FROM warehouse.fact_player_season_metric WHERE is_season_total "
            "AND family = %s AND metric = %s AND player_id = %s",
            [family, metric, player_id],
        ).fetchall()
    expected = [(t.name, 0, 0, 0, gold[t.name]) for t in TABLES[:-1]]
    expected.append((FACT.name, 0, 1, 0, gold[FACT.name] - 1))
    assert _counts(counts) == expected
    key = ("basketball", family, metric, player_id, None, None, True)
    assert _written(before, after) == {key}
    assert stored == [(value + 1,)]


def test_a_removed_player_deletes_his_rows(pg_dsn: str, tmp_gold: Path) -> None:
    gold = _gold_rows(tmp_gold)
    fact_file = (tmp_gold / "gold" / FACT.gold / "data.parquet").as_posix()
    with duckdb.connect() as con:
        player_id, rows = con.execute(
            "SELECT player_id, count(*) FROM read_parquet(?) WHERE sport = 'football' "
            "GROUP BY player_id ORDER BY count(*) DESC, player_id LIMIT 1",
            [fact_file],
        ).fetchall()[0]
    with connect(pg_dsn) as conn:
        migrate(conn)
        load(conn, tmp_gold)
        for model in (FACT.gold, DIM_PLAYER.gold):
            _rewrite(
                tmp_gold,
                model,
                f"SELECT * FROM {{src}} WHERE NOT (sport = 'football' AND player_id = {player_id})",
            )
        counts = load(conn, tmp_gold)
        left = conn.execute(
            "SELECT count(*) FROM warehouse.fact_player_season_metric "
            "WHERE sport = 'football' AND player_id = %s",
            [player_id],
        ).fetchone()
    assert rows > 1
    assert _counts(counts) == [
        (DIM_PLAYER.name, 0, 0, 1, gold[DIM_PLAYER.name] - 1),
        *[(t.name, 0, 0, 0, gold[t.name]) for t in TABLES[1:-1]],
        (FACT.name, 0, 0, rows, gold[FACT.name] - rows),
    ]
    assert left == (0,)


def test_the_reader_reads_every_table_and_cannot_write_to_them_or_run_long(
    loaded_dsn: str,
) -> None:
    password = secrets.token_urlsafe(24)
    with connect(loaded_dsn) as conn:
        set_reader_password(conn, password)
    reader = make_conninfo(loaded_dsn, user=READER_ROLE, password=password)
    with psycopg.connect(reader, autocommit=True) as r:
        assert r.execute("SHOW statement_timeout").fetchone() == ("2s",)
        assert r.execute("SHOW default_transaction_read_only").fetchone() == ("on",)
        for t in TABLES:
            row = r.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("warehouse", t.name))
            ).fetchone()
            assert row is not None and row[0] > 0
        writes = [
            "INSERT INTO warehouse.dim_team VALUES ('x', -1, 'x', '\\x00')",
            "UPDATE warehouse.fact_player_season_metric SET value = 0",
            "DELETE FROM warehouse.dim_metric",
            "TRUNCATE warehouse.load_log",
            "CREATE TABLE warehouse.scratch (a int)",
        ]
        for statement in writes:
            # Read-only is only the default: a client can open a read-write transaction, and the
            # privileges still refuse the write.
            with pytest.raises(errors.InsufficientPrivilege), r.transaction():
                r.execute("SET TRANSACTION READ WRITE")
                r.execute(statement.encode())
        with pytest.raises(errors.QueryCanceled):
            r.execute("SELECT pg_sleep(3)")


def test_the_reader_cannot_create_temporary_tables_and_the_owner_still_can(
    owned_dsn: tuple[str, str],
) -> None:
    """Review V of P4, M1. PUBLIC holds TEMPORARY on every database, and read only is just the
    reader's default: in a transaction opened read-write it created temporary tables until 002
    revoked that. The database's owner, not a superuser here as on Neon, still stages the load in
    temporary tables."""
    dsn, as_owner = owned_dsn
    password = secrets.token_urlsafe(24)
    with connect(dsn) as conn:
        assert "002_no_temporary_tables" in migrate(conn)
        set_reader_password(conn, password)
    as_reader = make_conninfo(dsn, user=READER_ROLE, password=password)
    with psycopg.connect(as_reader, autocommit=True) as r:
        with pytest.raises(errors.InsufficientPrivilege), r.transaction():
            r.execute("SET TRANSACTION READ WRITE")
            r.execute("CREATE TEMP TABLE scratch AS SELECT 1 AS a")
    with psycopg.connect(as_owner, autocommit=True) as o, o.transaction():
        o.execute("CREATE TEMP TABLE stage (a int) ON COMMIT DROP")
