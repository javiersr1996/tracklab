"""`tracklab load postgres`: the gold dimensional model into Postgres, incrementally (task 44, P4).

The same truth the browser reads as Parquet, loaded the other way: four gold tables
(`dim_player`, `dim_season_team` as `dim_team`, `dim_metric` and the long fact) into the
`warehouse` schema. Every row carries `row_hash`, a fingerprint of all its columns. A load copies
each gold table into a temporary table and compares it with Postgres by key and fingerprint, in
one transaction: it inserts the keys that are new, updates the rows whose fingerprint changed,
deletes the keys gold no longer has and leaves the rest alone (decision 8 of the P4 plan). A second
load of the same gold writes no row of the four tables; `warehouse.load_log` keeps what each load
did.

The schema comes from the numbered files in `pipeline/sql/`, each applied once and recorded with
its sha256. The connection string is read from an environment variable named on the command line,
never from an argument, and nothing here prints it.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import TupleRow

SQL_DIR = Path(__file__).resolve().parents[3] / "sql"
SCHEMA = "warehouse"
READER_ROLE = "warehouse_reader"
# pg_advisory_xact_lock key: one migration or load at a time per database.
LOCK_KEY = 44

Connection = psycopg.Connection[TupleRow]


class LoadError(Exception):
    pass


@dataclass(frozen=True)
class Table:
    name: str
    gold: str
    key: tuple[str, ...]
    values: tuple[str, ...]
    # Key columns that can be NULL: compared with IS NOT DISTINCT FROM, the others with `=`.
    nullable_key: tuple[str, ...] = ()

    @property
    def columns(self) -> tuple[str, ...]:
        return self.key + self.values


# Parents before children: new rows go in this order and deleted rows in the reverse one, so no
# foreign key breaks inside the transaction.
TABLES: tuple[Table, ...] = (
    Table(
        "dim_player",
        "dim_player",
        ("sport", "player_id"),
        ("player_name", "player_short_name", "player_birthdate"),
    ),
    Table("dim_team", "dim_season_team", ("sport", "team_id"), ("team_name",)),
    Table("dim_metric", "dim_metric", ("sport", "family", "metric"), ("kind",)),
    Table(
        "fact_player_season_metric",
        "fact_player_season_metric",
        ("sport", "family", "metric", "player_id", "team_id", "position_group", "is_season_total"),
        ("value",),
        nullable_key=("team_id", "position_group"),
    ),
)


@dataclass(frozen=True)
class Counts:
    table: str
    inserted: int
    updated: int
    deleted: int
    unchanged: int

    def line(self) -> str:
        return (
            f"{self.table} inserted={self.inserted} updated={self.updated} "
            f"deleted={self.deleted} unchanged={self.unchanged}"
        )


def row_hash(row: Sequence[Any]) -> bytes:
    """Fingerprint of a row: 16 bytes of sha256 over its JSON text (floats by their shortest
    round-trip repr, dates in ISO format), so the same values hash the same on any machine."""
    text = json.dumps(list(row), default=str, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).digest()[:16]


def gold_file(data_dir: Path, table: Table) -> Path:
    path = data_dir / "gold" / table.gold / "data.parquet"
    if not path.is_file():
        raise LoadError(f"gold {table.gold} not found under the data root: build gold first")
    return path


def gold_rows(data_dir: Path, table: Table) -> list[tuple[Any, ...]]:
    columns = ", ".join(f'"{c}"' for c in table.columns)
    with duckdb.connect() as con:
        return con.execute(
            f"SELECT {columns} FROM read_parquet(?)", [gold_file(data_dir, table).as_posix()]
        ).fetchall()


def env_value(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise LoadError(f"${name} is not set")
    return value


def connect(dsn: str) -> Connection:
    try:
        conninfo_to_dict(dsn)
    except psycopg.ProgrammingError:
        # libpq quotes the part it cannot read, which may be the password (review V of P4, B2).
        raise LoadError(
            "the connection string cannot be parsed (a character may need percent-encoding)"
        ) from None
    return psycopg.connect(dsn, autocommit=True)


def _target(table: Table) -> sql.Identifier:
    return sql.Identifier(SCHEMA, table.name)


def _stage(table: Table) -> sql.Identifier:
    return sql.Identifier(f"stage_{table.name}")


def _same_key(table: Table) -> sql.Composed:
    parts = [
        sql.SQL(
            "t.{0} IS NOT DISTINCT FROM s.{0}" if c in table.nullable_key else "t.{0} = s.{0}"
        ).format(sql.Identifier(c))
        for c in table.key
    ]
    return sql.SQL(" AND ").join(parts)


def _columns(prefix: str | None, names: Sequence[str]) -> sql.Composed:
    return sql.SQL(", ").join(
        sql.Identifier(prefix, n) if prefix else sql.Identifier(n) for n in names
    )


def migrate(conn: Connection, sql_dir: Path = SQL_DIR) -> list[str]:
    """Apply, in order, the numbered SQL files not applied yet; refuse if an applied one changed."""
    applied: list[str] = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_KEY])
        conn.execute("CREATE SCHEMA IF NOT EXISTS warehouse")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS warehouse.schema_migrations (version text PRIMARY KEY, "
            "sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done: dict[str, str] = dict(
            conn.execute("SELECT version, sha256 FROM warehouse.schema_migrations").fetchall()
        )
        for path in sorted(sql_dir.glob("[0-9][0-9][0-9]_*.sql")):
            text = path.read_bytes()
            digest = hashlib.sha256(text).hexdigest()
            if path.stem in done:
                if done[path.stem] != digest:
                    raise LoadError(
                        f"{path.name} changed after it was applied: add a new numbered file"
                    )
                continue
            conn.execute(text)
            conn.execute(
                "INSERT INTO warehouse.schema_migrations (version, sha256) VALUES (%s, %s)",
                [path.stem, digest],
            )
            applied.append(path.stem)
    return applied


def set_reader_password(conn: Connection, password: str) -> None:
    """Let the read-only role log in. Neon takes passwords in plain text only ("Hashed passwords
    are not supported"), so it goes as a literal over the connection's TLS."""
    conn.execute(
        sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
            sql.Identifier(READER_ROLE), sql.Literal(password)
        )
    )


def _copy_to_stage(conn: Connection, table: Table, rows: list[tuple[Any, ...]]) -> None:
    conn.execute(
        sql.SQL("CREATE TEMP TABLE {} (LIKE {}) ON COMMIT DROP").format(
            _stage(table), _target(table)
        )
    )
    copy_sql = sql.SQL("COPY {} ({}) FROM STDIN").format(
        _stage(table), _columns(None, (*table.columns, "row_hash"))
    )
    with conn.cursor().copy(copy_sql) as copy:
        for row in rows:
            copy.write_row(row)
    # Sorted once by key, so the three comparisons below merge two indexes instead of sorting the
    # staged rows each time (measured on the fact: 3.7 s against 5.9 s).
    conn.execute(
        sql.SQL("CREATE INDEX ON {} ({})").format(_stage(table), _columns(None, table.key))
    )
    conn.execute(sql.SQL("ANALYZE {}").format(_stage(table)))


def _update_and_insert(conn: Connection, table: Table) -> tuple[int, int]:
    changing = (*table.values, "row_hash")
    updated = conn.execute(
        sql.SQL(
            "UPDATE {target} AS t SET ({cols}) = ROW({src}) FROM {stage} AS s "
            "WHERE {same} AND t.row_hash <> s.row_hash"
        ).format(
            target=_target(table),
            cols=_columns(None, changing),
            src=_columns("s", changing),
            stage=_stage(table),
            same=_same_key(table),
        )
    ).rowcount
    every = (*table.columns, "row_hash")
    inserted = conn.execute(
        sql.SQL(
            "INSERT INTO {target} ({cols}) SELECT {src} FROM {stage} AS s "
            "WHERE NOT EXISTS (SELECT FROM {target} AS t WHERE {same})"
        ).format(
            target=_target(table),
            cols=_columns(None, every),
            src=_columns("s", every),
            stage=_stage(table),
            same=_same_key(table),
        )
    ).rowcount
    return updated, inserted


def _delete_gone(conn: Connection, table: Table) -> int:
    return conn.execute(
        sql.SQL(
            "DELETE FROM {target} AS t WHERE NOT EXISTS (SELECT FROM {stage} AS s WHERE {same})"
        ).format(target=_target(table), stage=_stage(table), same=_same_key(table))
    ).rowcount


def load(conn: Connection, data_dir: Path) -> list[Counts]:
    """One incremental load of gold, in one transaction; returns what it wrote per table."""
    staged = {t.name: [(*row, row_hash(row)) for row in gold_rows(data_dir, t)] for t in TABLES}
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_KEY])
        for t in TABLES:
            _copy_to_stage(conn, t, staged[t.name])
        written = {t.name: _update_and_insert(conn, t) for t in TABLES}
        deleted = {t.name: _delete_gone(conn, t) for t in reversed(TABLES)}
        counts = []
        for t in TABLES:
            updated, inserted = written[t.name]
            unchanged = len(staged[t.name]) - updated - inserted
            counts.append(Counts(t.name, inserted, updated, deleted[t.name], unchanged))
        conn.cursor().executemany(
            "INSERT INTO warehouse.load_log VALUES (now(), %s, %s, %s, %s, %s)",
            [(c.table, c.inserted, c.updated, c.deleted, c.unchanged) for c in counts],
        )
        # Fresh statistics for the planner, only where something changed: a load that writes
        # nothing leaves the tables as they were.
        for t, c in zip(TABLES, counts, strict=True):
            if c.inserted or c.updated or c.deleted:
                conn.execute(sql.SQL("ANALYZE {}").format(_target(t)))
    return counts


def run_load_postgres(data_dir: Path, dsn_env: str, reader_password_env: str | None = None) -> int:
    started = time.perf_counter()
    try:
        dsn = env_value(dsn_env)
        password = env_value(reader_password_env) if reader_password_env else None
        with connect(dsn) as conn:
            for version in migrate(conn):
                print(f"load postgres: applied {version}")
            if password is not None:
                set_reader_password(conn, password)
                print(f"load postgres: {READER_ROLE} can log in")
            counts = load(conn, data_dir)
    except (LoadError, psycopg.Error) as error:
        print(f"load postgres: {error}")
        return 1
    for c in counts:
        print(f"load postgres: {c.line()}")
    print(f"load postgres: {time.perf_counter() - started:.1f} s")
    return 0
