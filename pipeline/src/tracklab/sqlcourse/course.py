"""`tracklab sql course`: the exercises of /sql, checked against their reference queries (task 99).

Each lesson is a folder `sqlcourse/<slug>/` with `example.sql` (the worked example, whose full
result the page shows, at most 20 rows), `facts.sql` (one query whose rows are `(fact, value)`:
the numbers the lesson's prose prints, so none is typed by hand) and one `<n>.sql` per exercise:
a header of `-- key: value` lines (`prompt`, `hint` one or more, `ordered: true|false`,
`order_key: col [DESC], col [DESC]` when ordered; a line `--` and two or more spaces continues the
line above) followed by the reference query.

Every query runs in a fresh DuckDB connection that holds only the seven views of `/warehouse`,
created as `web/lib/warehouse/registry.ts` creates them, and locked as the browser's engine is
(`allowed_paths` the seven files, no external access). The guards: a reference returns at most
1,000 rows (the engine's `ROW_LIMIT`); an ordered one's `order_key` columns are columns of its
result, unique in it, and its rows are sorted by them (NULLs last, as DuckDB sorts), so no tie is
left to the engine; no query names `read_`, a quoted path or a URL, and each passes the
read-only gate of `sql.ts` (`gate.py`); no value is NaN, Infinity or too large to normalize; the
example has at most 20 rows. Any guard that fails stops the writer and fails `--check`.

`web/public/data/sql/course.json` carries, per lesson, the example (its SQL, column names and
rows as JSON gives them), the facts and, per exercise, its prompt, hints, reference SQL, whether
it is ordered, its column and row counts and the SHA-256 of its normalized result (`normalize.py`).
`--check` rebuilds the file and compares it byte for byte: `FULL k/k` when all of `LESSONS` are
written, `PARTIAL k/n` while some lesson has no folder yet.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from tracklab.sqlcourse.gate import SqlSyntaxError, check_sql, tokenize
from tracklab.sqlcourse.normalize import NotComparable, fingerprint, normalize, parse_row, wrap

LESSONS = (
    "select",
    "where",
    "expressions",
    "group-by",
    "joins",
    "long-wide",
    "windows",
    "scouting",
)
HERE = Path(__file__).parent
SCHEMA_VERSION = 1
ROW_LIMIT = 1000  # `ROW_LIMIT` of web/lib/duckdb/engine.ts
EXAMPLE_ROWS = 20

# registry.ts: the names end up inside SQL, so they are checked rather than quoted.
TABLE_NAME = re.compile(r"[a-z][a-z0-9_]*")
FILE_NAME = re.compile(r"([a-z][a-z0-9_]*)\.[0-9a-f]{8}\.parquet")

KEY_LINE = re.compile(r"-- (prompt|hint|ordered|order_key): (\S.*)")
CONTINUED = re.compile(r"-- {2,}(\S.*)")
EXERCISE_FILE = re.compile(r"([1-9][0-9]*)\.sql")
READS_A_FILE = re.compile(r"\bread_", re.IGNORECASE)
LOOKS_LIKE_PATH = re.compile(r"[/\\]|\.[A-Za-z][A-Za-z0-9]*$")
ORDER_COLUMN = re.compile(r"(\S+)(?:\s+(ASC|DESC))?", re.IGNORECASE)


@dataclass(frozen=True)
class Exercise:
    prompt: str
    hints: list[str]
    ordered: bool
    order_key: list[str]
    descending: list[bool]  # one per `order_key` column
    sql: str


@dataclass(frozen=True)
class Result:
    columns: list[str]
    rows: list[str]  # one JSON array per row, as the wrapper gives it


def parse(text: str) -> Exercise:
    """The header and the reference query of an exercise file."""
    if "\r" in text:
        raise ValueError("CR line ends")
    lines = text.split("\n")
    fields: list[tuple[str, str]] = []
    end = 0
    for end, line in enumerate(lines):
        if not line.startswith("--"):
            break
        if (key := KEY_LINE.fullmatch(line)) is not None:
            fields.append((key.group(1), key.group(2).rstrip()))
        elif (more := CONTINUED.fullmatch(line)) is not None and fields:
            name, value = fields[-1]
            fields[-1] = (name, f"{value} {more.group(1).rstrip()}")
        else:
            raise ValueError(f"header line {end + 1} is not `-- key: value` or a continuation")
    else:
        end = len(lines)
    sql = "\n".join(lines[end:]).strip()

    def one(name: str) -> str | None:
        values = [v for k, v in fields if k == name]
        if len(values) > 1:
            raise ValueError(f"`{name}` given {len(values)} times")
        return values[0] if values else None

    prompt, ordered, order_key = one("prompt"), one("ordered"), one("order_key")
    hints = [v for k, v in fields if k == "hint"]
    if prompt is None or not hints or ordered not in ("true", "false"):
        raise ValueError("needs `prompt`, at least one `hint` and `ordered: true|false`")
    if (ordered == "true") != (order_key is not None):
        raise ValueError("`order_key` goes with `ordered: true`, and only with it")
    columns = [ORDER_COLUMN.fullmatch(c.strip()) for c in (order_key or "").split(",")]
    if order_key is not None and any(c is None for c in columns):
        raise ValueError("`order_key` is not `col [ASC|DESC], ...`")
    keys = [(c.group(1), (c.group(2) or "").upper() == "DESC") for c in columns if c is not None]
    if not sql:
        raise ValueError("no reference query after the header")
    return Exercise(
        prompt, hints, ordered == "true", [k for k, _ in keys], [d for _, d in keys], sql
    )


def warehouse(public: Path) -> list[tuple[str, Path]]:
    """The seven tables of `web/public/data/warehouse.json` and their files, checked as
    registry.ts checks them."""
    manifest = json.loads((public / "data" / "warehouse.json").read_text("utf-8"))
    seen: set[str] = set()
    out = []
    for entry in manifest["tables"]:
        table, file = entry["table"], entry["file"]
        name = FILE_NAME.fullmatch(file)
        if TABLE_NAME.fullmatch(table) is None or table in seen or name is None:
            raise ValueError(f"warehouse.json: table {table!r}, file {file!r}")
        if name.group(1) != table:
            raise ValueError(f"warehouse.json: file {file!r} for table {table!r}")
        seen.add(table)
        out.append((table, public / "data" / "warehouse" / file))
    return out


def connect(public: Path) -> duckdb.DuckDBPyConnection:
    """A fresh connection with the seven views and nothing else, locked like the browser's
    engine (web/lib/duckdb/engine.ts): only the seven files may be opened, and no setting changed
    back. Python's replacement scans (a DataFrame read by its variable name) are off."""
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    con.execute("SET python_enable_replacements = false")
    paths = []
    for table, file in warehouse(public):
        path = file.resolve().as_posix().replace("'", "''")
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{path}')")
        paths.append(f"'{path}'")
    con.execute(f"SET allowed_paths = [{', '.join(paths)}]")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def run(con: duckdb.DuckDBPyConnection, query: str) -> Result:
    columns = list(con.sql(query.strip().rstrip(";")).columns)
    rows = [str(r[0]) for r in con.execute(wrap(query)).fetchall()]
    return Result(columns, rows)


def text_problems(sql: str, tables: list[str]) -> list[str]:
    """What the reference's text breaks: the read-only gate, a `read_`, a quoted path or URL."""
    gate = check_sql(sql, tables)
    problems = [] if gate.ok else [f"the read-only gate says: {gate.reason}"]
    if READS_A_FILE.search(sql):
        problems.append("names a read_ function: the course reads the seven tables by name")
    try:
        tokens = tokenize(sql)
    except SqlSyntaxError:
        return problems  # the gate said so
    for t in tokens:
        if t.kind in ("string", "identifier") and LOOKS_LIKE_PATH.search(t.text):
            problems.append(f"{json.dumps(t.text)} looks like a path or URL")
    return problems


def value_problems(result: Result) -> list[str]:
    try:
        normalize(result.rows, ordered=True)
    except NotComparable as error:
        return [f"a value the checker cannot compare: {error}"]
    return []


def exercise_problems(exercise: Exercise, result: Result) -> list[str]:
    """The guards on a reference's result."""
    problems = value_problems(result)
    if len(result.rows) > ROW_LIMIT:
        problems.append(f"{len(result.rows)} rows, more than the engine's {ROW_LIMIT}")
    if exercise.ordered:
        absent = [k for k in exercise.order_key if result.columns.count(k) != 1]
        if absent:
            problems.append(f"order_key {absent} is not one column of the result {result.columns}")
        else:
            at = [result.columns.index(k) for k in exercise.order_key]
            keys = [[row[i] for i in at] for row in map(parse_row, result.rows)]
            seen: set[str] = set()
            for key in map(json.dumps, keys):
                if key in seen:
                    problems.append(
                        f"order_key {exercise.order_key} ties on {key}: the order is the engine's"
                    )
                    break
                seen.add(key)
            n = next(
                (n for n in range(1, len(keys)) if not _before(keys[n - 1], keys[n], exercise)), 0
            )
            if n:
                problems.append(
                    f"rows {n} and {n + 1} are not sorted by order_key {exercise.order_key}"
                )
    return problems


def _before(a: list[Any], b: list[Any], exercise: Exercise) -> bool:
    """Whether key `a` may come before key `b`: the first column where they differ decides, in
    its direction, with NULLs last either way (DuckDB's `default_null_order`); text compares by
    code point, as DuckDB's binary collation does."""
    for x, y, desc in zip(a, b, exercise.descending, strict=True):
        if x == y:
            continue
        if x is None or y is None:
            return y is None
        return bool(x > y) if desc else bool(x < y)
    return True


def lesson_files(folder: Path) -> tuple[list[tuple[int, Path]], list[str]]:
    problems = [f"no {n}" for n in ("example.sql", "facts.sql") if not (folder / n).is_file()]
    numbered = []
    for path in sorted(folder.iterdir()):
        if path.name in ("example.sql", "facts.sql"):
            continue
        if (n := EXERCISE_FILE.fullmatch(path.name)) is None:
            problems.append(f"{path.name} is not example.sql, facts.sql or <n>.sql")
        else:
            numbered.append((int(n.group(1)), path))
    numbered.sort()
    if not numbered:
        problems.append("no exercise")
    elif [n for n, _ in numbered] != list(range(1, len(numbered) + 1)):
        problems.append(f"exercises {[n for n, _ in numbered]} are not numbered 1 to n")
    return numbered, problems


def _read(path: Path) -> str:
    text = path.read_bytes().decode("utf-8")
    if "\r" in text:
        raise ValueError("CR line ends")
    return text.strip()


def _query(
    con: duckdb.DuckDBPyConnection, sql: str, tables: list[str], where: str, problems: list[str]
) -> Result | None:
    """The result of one query after the text guards, or None with the problems added."""
    found = text_problems(sql, tables)
    if not found:
        try:
            result = run(con, sql)
        except duckdb.Error as error:
            found = [f"fails: {str(error).splitlines()[0]}"]
        else:
            found = value_problems(result)
            if not found:
                return result
    problems += [f"{where}: {p}" for p in found]
    return None


def build_lesson(
    slug: str, folder: Path, con: duckdb.DuckDBPyConnection, tables: list[str]
) -> tuple[dict[str, Any], list[str]]:
    numbered, problems = lesson_files(folder)
    if problems:
        return {}, [f"{slug}: {p}" for p in problems]

    example_sql = _read(folder / "example.sql")
    example = _query(con, example_sql, tables, f"{slug}/example.sql", problems)
    if example is not None and len(example.rows) > EXAMPLE_ROWS:
        problems.append(f"{slug}/example.sql: {len(example.rows)} rows, more than {EXAMPLE_ROWS}")

    facts: dict[str, Any] = {}
    result = _query(con, _read(folder / "facts.sql"), tables, f"{slug}/facts.sql", problems)
    if result is not None:
        rows = [parse_row(t) for t in result.rows]
        names = [r[0] for r in rows]
        if len(result.columns) != 2 or not all(isinstance(n, str) and n for n in names):
            problems.append(f"{slug}/facts.sql: rows are not (fact, value) with a fact name")
        elif len(set(names)) != len(names):
            problems.append(f"{slug}/facts.sql: a fact name repeats")
        else:
            facts = dict(sorted((r[0], r[1]) for r in rows))

    exercises = []
    for n, path in numbered:
        where = f"{slug}/{path.name}"
        try:
            exercise = parse(path.read_bytes().decode("utf-8"))
        except ValueError as error:
            problems.append(f"{where}: {error}")
            continue
        result = _query(con, exercise.sql, tables, where, problems)
        if result is None:
            continue
        found = exercise_problems(exercise, result)
        if found:
            problems += [f"{where}: {p}" for p in found]
            continue
        _, sha256 = fingerprint(result.rows, exercise.ordered)
        exercises.append(
            {
                "id": f"{slug}-{n}",
                "prompt": exercise.prompt,
                "hints": exercise.hints,
                "solution": exercise.sql,
                "ordered": exercise.ordered,
                "columns": len(result.columns),
                "rows": len(result.rows),
                "sha256": sha256,
            }
        )
    if problems or example is None:
        return {}, problems
    lesson = {
        "slug": slug,
        "example": {
            "sql": example_sql,
            "columns": example.columns,
            "rows": [parse_row(t) for t in example.rows],
        },
        "facts": facts,
        "exercises": exercises,
    }
    return lesson, []


def build(public: Path, source: Path = HERE) -> tuple[dict[str, Any], list[str], list[str]]:
    """The payload of course.json, the problems found and the lessons with no folder yet."""
    tables = [table for table, _ in warehouse(public)]
    problems = [
        f"{p.name}/ is a lesson folder not in LESSONS"
        for p in sorted(source.iterdir())
        if p.is_dir() and p.name not in LESSONS and any(p.glob("*.sql"))
    ]
    lessons, missing = [], []
    for slug in LESSONS:
        folder = source / slug
        if not folder.is_dir():
            missing.append(slug)
            continue
        with connect(public) as con:
            lesson, found = build_lesson(slug, folder, con, tables)
        problems += found
        if lesson:
            lessons.append(lesson)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "duckdb_version": duckdb.__version__,
        "lessons": lessons,
    }
    return payload, problems, missing


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _first_difference(a: bytes, b: bytes) -> int:
    """The 1-based line of the first byte where `a` and `b` differ."""
    at = next(
        (i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), min(len(a), len(b))
    )
    return a[:at].count(b"\n") + 1


def run_sql_course(public: Path, *, check: bool = False, source: Path = HERE) -> int:
    payload, problems, missing = build(public, source)
    command = "sql course --check" if check else "sql course"
    for lesson in payload["lessons"]:
        for e in lesson["exercises"]:
            print(
                f"sql course {e['id']}: {e['rows']} rows x {e['columns']} columns, "
                f"{'ordered' if e['ordered'] else 'unordered'}, sha256 {e['sha256'][:12]}"
            )
    for slug in missing:
        print(f"sql course: lesson {slug} has no folder sqlcourse/{slug}/ yet")
    if problems:
        for p in problems:
            print(f"sql course: {p}")
        print(f"{command}: {len(problems)} problem(s); nothing written")
        return 1

    text = render(payload).encode("utf-8")
    out = public / "data" / "sql" / "course.json"
    done, total = len(payload["lessons"]), len(LESSONS)
    exercises = sum(len(lesson["exercises"]) for lesson in payload["lessons"])
    if not check:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(text)
        print(
            f"sql course: {out} ({len(text)} bytes), {done}/{total} lessons, {exercises} exercises"
        )
        return 0
    if not out.is_file():
        print(f"{command}: no {out}")
        return 1
    on_disk = out.read_bytes()
    if on_disk != text:
        line = _first_difference(on_disk, text)
        print(f"{command}: {out.name} differs from what the references give (line {line})")
        return 1
    what = (
        f"{out.name} equal byte for byte to the one rebuilt from the Parquet files of /warehouse, "
        f"{exercises} exercises past every guard"
    )
    if done == total:
        print(f"{command}: FULL {done}/{total}: {what}")
    else:
        print(f"{command}: PARTIAL {done}/{total}: {what}; no folder yet: {', '.join(missing)}")
    return 0
