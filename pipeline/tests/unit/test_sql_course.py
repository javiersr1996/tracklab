"""`tracklab sql course` (task 99): the fingerprint, the gate's port, the guards and the writer.

`web/public/data` is in git, so these run on the real Parquet files of /warehouse everywhere. The
normalization is checked against `web/tests/fixtures/sql-normalize.json`, whose expected values
were computed by the rule written in JavaScript, not by this code. Each guard is shown failing on
a reference planted to break it, through the same path the writer takes (`build_lesson`), and
the writer and `--check` both refuse a lesson with a planted problem.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import duckdb
import pytest

from tracklab.sqlcourse.course import (
    HERE,
    LESSONS,
    build,
    build_lesson,
    connect,
    parse,
    render,
    run_sql_course,
    warehouse,
)
from tracklab.sqlcourse.gate import check_sql
from tracklab.sqlcourse.normalize import NotComparable, fingerprint, wrap

REPO = Path(__file__).resolve().parents[3]
PUBLIC = REPO / "web" / "public"
FIXTURES = json.loads(
    (REPO / "web" / "tests" / "fixtures" / "sql-normalize.json").read_text("utf-8")
)
TABLES = [table for table, _ in warehouse(PUBLIC)]
SELECT = HERE / "select"


# The normalization, against the shared fixtures.


def test_the_fixtures_cover_values_and_rejections() -> None:
    cases = FIXTURES["cases"]
    assert sum(not c["rejected"] for c in cases) >= 15
    assert sum(c["rejected"] for c in cases) >= 5


@pytest.mark.parametrize("case", FIXTURES["cases"], ids=lambda c: c["name"])
def test_normalization_matches_the_shared_fixtures(case: dict[str, Any]) -> None:
    if case["rejected"]:
        with pytest.raises(NotComparable):
            fingerprint(case["rows"], case["ordered"])
    else:
        assert fingerprint(case["rows"], case["ordered"]) == (case["canonical"], case["sha256"])


def test_the_wrapper_strips_the_semicolon_and_survives_a_trailing_comment() -> None:
    con = duckdb.connect()
    sql = "SELECT 10 AS a, '10' AS b, NULL AS c -- a comment\n;"
    assert wrap(sql).startswith("SELECT json_array(*COLUMNS(*))::VARCHAR FROM (")
    assert [r[0] for r in con.execute(wrap(sql)).fetchall()] == ['[10,"10",null]']


# The read-only gate, on the cases of web/tests/warehouse-sql.test.ts.

GATE_TABLES = ["bb_shots", "fb_physical", "fact"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select * from fact limit 5",
        "WITH t AS (SELECT * FROM bb_shots) SELECT count(*) FROM t",
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 3) "
        "SELECT * FROM n",
        "EXPLAIN SELECT * FROM fact WHERE metric = 'handler_ppp'",
        "EXPLAIN ANALYZE SELECT quantile_cont(value, 0.9) FROM fact",
        "explain analyze with t as (select 1) select * from t",
        "(SELECT 1) UNION ALL (SELECT 2)",
        "SELECT 1;",
        "SELECT 1;  ;\n",
        "SELECT 'LOAD this' AS x",
        "-- INSTALL httpfs\nSELECT 1",
        "/* ATTACH 'x.db'; COPY */ SELECT 1",
        'SELECT 1 AS "set"',
        "SELECT 'it''s; INSTALL httpfs' AS x",
        "SELECT 1 AS a --\r\nFROM fact",
        "SELECT * FROM (PIVOT fact ON family USING count(*))",
    ],
)
def test_the_gate_admits(sql: str) -> None:
    check = check_sql(sql, GATE_TABLES)
    assert check.ok, check.reason


@pytest.mark.parametrize(
    ("sql", "why"),
    [
        ("INSTALL httpfs", "Only SELECT"),
        ("FORCE INSTALL httpfs", "Only SELECT"),
        ("LOAD parquet", "Only SELECT"),
        ("ATTACH 'other.duckdb'", "Only SELECT"),
        ("COPY (SELECT 1) TO 'out.csv'", "Only SELECT"),
        ("SET enable_external_access = true", "Only SELECT"),
        ("PRAGMA version", "Only SELECT"),
        ("CREATE VIEW v AS SELECT 1", "Only SELECT"),
        ("DROP VIEW fact", "Only SELECT"),
        ("DESCRIBE fact", "Only SELECT"),
        ("EXPLAIN ANALYZE COPY (SELECT 1) TO 'out.csv'", "Only SELECT"),
        ("PIVOT fact ON family USING count(*)", "Only SELECT"),
        ("WITH t AS (SELECT 1) INSERT INTO fact SELECT * FROM t", "INSERT is not allowed"),
        ("EXPLAIN ANALYZE SELECT 1 FROM (LOAD parquet)", "LOAD is not allowed"),
        ("select 1 from x where y in (select 1) -- fine\n; attach 'x'", "One statement"),
        ("SELECT 1; INSTALL httpfs", "One statement at a time"),
        ("SELECT 1; SELECT 2", "One statement at a time"),
        ("SELECT 1 AS a --\r; INSTALL httpfs", "One statement at a time"),
        ("SELECT * FROM read_csv('https://example.com/x.csv')", "No URLs"),
        ("SELECT * FROM 'https://example.com/x.parquet'", "No URLs"),
        ('SELECT * FROM "s3://bucket/x.parquet"', "No URLs"),
        ("SELECT * FROM read_text($$http://example.com/$$)", "No URLs"),
        ("SELECT * FROM query('INSTALL httpfs')", r"query\(\) is not allowed"),
        ("SELECT * FROM query_table('fact')", r"query_table\(\) is not allowed"),
        ("", "Nothing to run"),
        ("  -- just a comment\n ; ", "Nothing to run"),
        ("SELECT 'open", "Unterminated string"),
        ('SELECT "open', "Unterminated identifier"),
        ("SELECT 1 /* open", "Unterminated comment"),
        ("SELECT $$open", "Unterminated dollar"),
    ],
)
def test_the_gate_rejects(sql: str, why: str) -> None:
    check = check_sql(sql, GATE_TABLES)
    assert not check.ok and re.search(why, check.reason), check.reason


def test_the_gate_names_the_tables_it_sees() -> None:
    sql = 'SELECT * FROM bb_shots JOIN "FACT" USING (player_id)'
    assert check_sql(sql, GATE_TABLES).tables == ["bb_shots", "fact"]
    sql = "SELECT 'fb_physical' AS fact_name FROM Fb_Physical"
    assert check_sql(sql, GATE_TABLES).tables == ["fb_physical"]


# The exercise header.


def test_the_header_is_parsed_with_its_continuations() -> None:
    ex = parse(
        "-- prompt: First line,\n--   and the rest.\n-- hint: One.\n-- hint: Two.\n"
        "-- ordered: true\n-- order_key: a DESC, b\nSELECT 1 AS a, 2 AS b\n"
    )
    assert ex.prompt == "First line, and the rest."
    assert ex.hints == ["One.", "Two."]
    assert ex.ordered and ex.order_key == ["a", "b"] and ex.descending == [True, False]
    assert ex.sql == "SELECT 1 AS a, 2 AS b"


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("-- prompt: p\n-- hint: h\nSELECT 1", "ordered: true"),
        ("-- prompt: p\n-- hint: h\n-- ordered: false\n-- order_key: a\nSELECT 1", "order_key"),
        ("-- prompt: p\n-- hint: h\n-- ordered: true\nSELECT 1", "order_key"),
        ("-- prompt: p\n-- hint: h\n-- ordered: true\n-- order_key: a,, b\nSELECT 1", "ASC"),
        ("-- prompt: p\n-- hint: h\n-- ordered: true\n-- order_key: a UP\nSELECT 1", "ASC"),
        ("-- prompt: p\n-- note: n\n-- hint: h\n-- ordered: false\nSELECT 1", "header line 2"),
        ("-- prompt: p\n-- prompt: q\n-- hint: h\n-- ordered: false\nSELECT 1", "2 times"),
        ("-- prompt: p\n-- hint: h\n-- ordered: false\n", "no reference query"),
        ("-- prompt: p\r\n-- hint: h\r\n-- ordered: false\r\nSELECT 1", "CR"),
    ],
)
def test_a_bad_header_is_refused(text: str, why: str) -> None:
    with pytest.raises(ValueError, match=why):
        parse(text)


# The guards, each on a planted reference.

GOOD_HEADER = "-- prompt: p\n-- hint: h\n"


def plant(root: Path, files: dict[str, str]) -> Path:
    """A copy of lesson 1 under `root/select/` with `files` written over it."""
    folder = root / "select"
    shutil.copytree(SELECT, folder)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8", newline="\n")
    return folder


def problems_of(tmp_path: Path, files: dict[str, str]) -> list[str]:
    with connect(PUBLIC) as con:
        lesson, problems = build_lesson("select", plant(tmp_path, files), con, TABLES)
    assert not lesson
    return problems


@pytest.mark.parametrize(
    ("name", "text", "why"),
    [
        (
            "1.sql",
            GOOD_HEADER + "-- ordered: true\n-- order_key: attempts DESC\n"
            "SELECT player_name, attempts FROM bb_shots ORDER BY attempts DESC LIMIT 11",
            r"select/1\.sql: order_key \['attempts'\] ties on \[325\]",
        ),
        (
            "1.sql",
            GOOD_HEADER + "-- ordered: true\n-- order_key: attempts\n"
            "SELECT player_name, attempts FROM bb_shots ORDER BY attempts DESC LIMIT 3",
            r"select/1\.sql: rows 1 and 2 are not sorted by order_key \['attempts'\]",
        ),
        (
            "1.sql",
            GOOD_HEADER + "-- ordered: true\n-- order_key: shots\n"
            "SELECT player_name, attempts FROM bb_shots ORDER BY attempts DESC LIMIT 3",
            r"order_key \['shots'\] is not one column",
        ),
        (
            "2.sql",
            GOOD_HEADER + "-- ordered: false\nSELECT * FROM fact LIMIT 1001",
            r"select/2\.sql: 1001 rows, more than the engine's 1000",
        ),
        (
            "2.sql",
            GOOD_HEADER + "-- ordered: false\nSELECT * FROM read_parquet('x')",
            "names a read_ function",
        ),
        (
            "2.sql",
            GOOD_HEADER + "-- ordered: false\nSELECT * FROM 'bb_shots.38163f30.parquet'",
            "looks like a path or URL",
        ),
        (
            "2.sql",
            GOOD_HEADER + "-- ordered: false\nDROP VIEW bb_shots",
            "the read-only gate says: Only SELECT, WITH, EXPLAIN run here",
        ),
        (
            "2.sql",
            GOOD_HEADER + "-- ordered: false\nSELECT 1; DROP VIEW bb_shots",
            "the read-only gate says: One statement at a time",
        ),
        (
            "2.sql",
            GOOD_HEADER + "-- ordered: false\nSELECT 'nan'::DOUBLE AS x FROM bb_shots LIMIT 1",
            "a value the checker cannot compare: nan",
        ),
        (
            "2.sql",
            GOOD_HEADER + "-- ordered: false\nSELECT max(attempts) * 1e12 AS x FROM bb_shots",
            "a value the checker cannot compare",
        ),
        (
            "2.sql",
            GOOD_HEADER + "-- ordered: false\nSELECT * FROM players",
            "fails: Catalog Error",
        ),
        (
            "example.sql",
            "SELECT player_name FROM bb_shots ORDER BY attempts DESC LIMIT 21",
            r"select/example\.sql: 21 rows, more than 20",
        ),
        (
            "facts.sql",
            "SELECT 'rows' AS fact, 1 AS value UNION ALL SELECT 'rows', 2",
            "a fact name repeats",
        ),
        ("3.sql", "-- prompt: p\nSELECT 1", "select/3.sql: needs `prompt`"),
        ("4.sql", GOOD_HEADER + "-- ordered: false\nSELECT 1", r"exercises \[1, 2, 4\]"),
        ("notes.txt", "x", "notes.txt is not example.sql"),
    ],
)
def test_each_guard_fails_on_a_planted_reference(
    tmp_path: Path, name: str, text: str, why: str
) -> None:
    problems = problems_of(tmp_path, {name: text})
    assert any(re.search(why, p) for p in problems), problems


def test_the_connection_holds_only_the_seven_views_and_opens_no_other_file() -> None:
    with connect(PUBLIC) as con:
        rows = con.execute("SELECT table_name FROM information_schema.tables").fetchall()
        names = [r[0] for r in rows]
        assert sorted(names) == sorted(TABLES) and len(names) == 7
        with pytest.raises(duckdb.PermissionException):
            con.execute("SELECT * FROM read_csv('pyproject.toml')")
        with pytest.raises(duckdb.InvalidInputException):
            con.execute("SET enable_external_access = true")


@pytest.fixture
def public(tmp_path: Path) -> Path:
    """A public folder with the real warehouse files and course.json, to break in a test."""
    root = tmp_path / "public"
    (root / "data" / "sql").mkdir(parents=True)
    shutil.copy(PUBLIC / "data" / "warehouse.json", root / "data" / "warehouse.json")
    shutil.copytree(PUBLIC / "data" / "warehouse", root / "data" / "warehouse")
    shutil.copy(PUBLIC / "data" / "sql" / "course.json", root / "data" / "sql" / "course.json")
    return root


@pytest.mark.parametrize("check", [False, True])
def test_the_writer_and_the_check_refuse_a_planted_problem(
    public: Path, tmp_path: Path, check: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source"
    plant(source, {"2.sql": GOOD_HEADER + "-- ordered: false\nSELECT * FROM fact LIMIT 1001"})
    before = (public / "data" / "sql" / "course.json").read_bytes()
    assert run_sql_course(public, check=check, source=source) == 1
    assert "1 problem(s); nothing written" in capsys.readouterr().out
    assert (public / "data" / "sql" / "course.json").read_bytes() == before


# The writer and --check on the real files.


def test_the_writer_is_deterministic() -> None:
    first, problems, _ = build(PUBLIC)
    second, _, _ = build(PUBLIC)
    assert problems == []
    assert render(first) == render(second)
    assert "\r" not in render(first)


def test_check_passes_on_the_real_files(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_sql_course(PUBLIC, check=True) == 0
    out = capsys.readouterr().out
    written = [slug for slug in LESSONS if (HERE / slug).is_dir()]
    total = len(LESSONS)
    if len(written) == total:
        assert f"--check: FULL {total}/{total}" in out
    else:
        assert f"--check: PARTIAL {len(written)}/{total}" in out
        missing = [slug for slug in LESSONS if slug not in written]
        assert all(f"lesson {slug} has no folder" in out for slug in missing)


def test_check_fails_when_one_byte_of_course_json_changes(
    public: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = public / "data" / "sql" / "course.json"
    assert run_sql_course(public, check=True) == 0
    data = bytearray(path.read_bytes())
    at = data.index(b'"sha256": "') + len(b'"sha256": "')
    data[at] = ord("1") if data[at] == ord("0") else ord("0")
    path.write_bytes(bytes(data))
    assert run_sql_course(public, check=True) == 1
    assert "course.json differs from what the references give" in capsys.readouterr().out


def test_a_missing_lesson_is_partial_not_full(
    public: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source"
    plant(source, {})
    assert run_sql_course(public, source=source) == 0
    assert run_sql_course(public, check=True, source=source) == 0
    out = capsys.readouterr().out
    assert f"PARTIAL 1/{len(LESSONS)}" in out and "FULL" not in out
    assert "lesson where has no folder sqlcourse/where/ yet" in out
