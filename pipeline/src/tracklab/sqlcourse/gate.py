"""The read-only gate of `/warehouse` (`web/lib/warehouse/sql.ts`, task 42), ported to Python.

`/sql` sends the reader's query through the same gate, so every reference query of the course
must pass it too: one SELECT, WITH or EXPLAIN statement, no keyword that writes, loads, attaches,
copies or configures, no table function that runs a SQL string and no URL. This is a line-by-line
port of `tokenize` and `checkSql`, rules and messages included; `tests/unit/test_sql_course.py`
runs the cases of `web/tests/warehouse-sql.test.ts` on it. Where the two languages differ the
port follows JavaScript: `\\s` is JavaScript's whitespace set, and a word is `\\p{L}` or `_`
followed by `\\p{L}`, `\\p{N}`, `_` or `$`, by Unicode category.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

READ_STATEMENTS = ("select", "with", "explain")

DENIED_WORDS = frozenset(
    {
        "alter",
        "attach",
        "call",
        "checkpoint",
        "copy",
        "create",
        "delete",
        "detach",
        "drop",
        "execute",
        "export",
        "import",
        "insert",
        "install",
        "load",
        "pragma",
        "prepare",
        "reset",
        "set",
        "truncate",
        "update",
        "use",
        "vacuum",
    }
)
DENIED_FUNCTIONS = frozenset({"query", "query_table"})
NO_URLS = "the tables are the files in warehouse.json, read by name."

# JavaScript's `\s`: WhiteSpace and LineTerminator of ECMAScript (Python's isspace() differs on
# U+FEFF and U+001C to U+001F).
JS_SPACE = frozenset(
    chr(c)
    for c in (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0xA0, 0x1680, *range(0x2000, 0x200B))
    + (0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF)
)
NUMBER = re.compile(r"[0-9][0-9_]*(\.[0-9_]*)?([eE][+-]?[0-9]+)?")
DOLLAR_TAG = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


@dataclass(frozen=True)
class Token:
    kind: str  # word, identifier, string, number, symbol
    text: str
    at: int  # where it starts in the SQL


@dataclass(frozen=True)
class SqlCheck:
    ok: bool
    reason: str = ""
    tables: list[str] = field(default_factory=list)


class SqlSyntaxError(Exception):
    pass


def _word_at(sql: str, at: int) -> str | None:
    """`[\\p{L}_][\\p{L}\\p{N}_$]*` at `at`."""
    if not (sql[at] == "_" or unicodedata.category(sql[at]).startswith("L")):
        return None
    end = at + 1
    while end < len(sql) and (sql[end] in "_$" or unicodedata.category(sql[end])[0] in "LN"):
        end += 1
    return sql[at:end]


def _quoted(sql: str, at: int, quote: str) -> tuple[str, int]:
    """A quoted run starting at `at`, with the quote doubled as its only escape."""
    text = ""
    start = at + 1
    while True:
        close = sql.find(quote, start)
        if close == -1:
            kind = "string" if quote == "'" else "identifier"
            raise SqlSyntaxError(f"Unterminated {kind}.")
        if sql[close + 1 : close + 2] == quote:
            text += sql[start : close + 1]
            start = close + 2
            continue
        return text + sql[start:close], close + 1


def tokenize(sql: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    while i < len(sql):
        c = sql[i]
        if c in JS_SPACE:
            i += 1
        elif sql.startswith("--", i):
            # Ends at `\r` as well as `\n`, as in DuckDB.
            ends = [k for k in (sql.find("\r", i), sql.find("\n", i)) if k != -1]
            i = min(ends) + 1 if ends else len(sql)
        elif sql.startswith("/*", i):
            # DuckDB nests block comments: `/* /* */ */` is one comment.
            depth = 1
            k = i + 2
            while depth > 0:
                opens = sql.find("/*", k)
                close = sql.find("*/", k)
                if close == -1:
                    raise SqlSyntaxError("Unterminated comment.")
                if opens != -1 and opens < close:
                    depth += 1
                    k = opens + 2
                else:
                    depth -= 1
                    k = close + 2
            i = k
        elif c in "'\"":
            text, end = _quoted(sql, i, c)
            tokens.append(Token("string" if c == "'" else "identifier", text, i))
            i = end
        elif (tag := DOLLAR_TAG.match(sql, i)) is not None:
            close = sql.find(tag.group(0), i + len(tag.group(0)))
            if close == -1:
                raise SqlSyntaxError("Unterminated dollar-quoted string.")
            tokens.append(Token("string", sql[i + len(tag.group(0)) : close], i))
            i = close + len(tag.group(0))
        elif (word := _word_at(sql, i)) is not None:
            tokens.append(Token("word", word, i))
            i += len(word)
        elif (number := NUMBER.match(sql, i)) is not None:
            tokens.append(Token("number", number.group(0), i))
            i += len(number.group(0))
        else:
            tokens.append(Token("symbol", c, i))
            i += 1
    return tokens


def _lower(t: Token | None) -> str | None:
    return t.text.lower() if t is not None and t.kind == "word" else None


def _is_symbol(t: Token | None, s: str) -> bool:
    return t is not None and t.kind == "symbol" and t.text == s


def _at(statement: list[Token], k: int) -> Token | None:
    return statement[k] if k < len(statement) else None


def _starts_with_read(statement: list[Token]) -> bool:
    """SELECT or WITH, after any opening parentheses; EXPLAIN [ANALYZE] in front of one."""
    k = 0
    while _is_symbol(_at(statement, k), "("):
        k += 1
    if _lower(_at(statement, k)) == "explain":
        k += 1
        if _lower(_at(statement, k)) == "analyze":
            k += 1
        while _is_symbol(_at(statement, k), "("):
            k += 1
    return _lower(_at(statement, k)) in ("select", "with")


def check_sql(sql: str, tables: tuple[str, ...] | list[str]) -> SqlCheck:
    """`checkSql` of sql.ts: ok with the registered tables the statement names, or a reason."""
    try:
        tokens = tokenize(sql)
    except SqlSyntaxError as error:
        return SqlCheck(False, str(error))

    statements: list[list[Token]] = [[]]
    for t in tokens:
        if _is_symbol(t, ";"):
            statements.append([])
        else:
            statements[-1].append(t)
    non_empty = [s for s in statements if s]
    if not non_empty:
        return SqlCheck(False, "Nothing to run: write a SELECT, WITH or EXPLAIN.")
    if len(non_empty) > 1:
        return SqlCheck(False, "One statement at a time.")
    [statement] = non_empty

    if not _starts_with_read(statement):
        names = ", ".join(s.upper() for s in READ_STATEMENTS)
        return SqlCheck(False, f"Only {names} run here.")
    for k, t in enumerate(statement):
        word = _lower(t)
        if word is not None and word in DENIED_WORDS:
            return SqlCheck(False, f"{t.text.upper()} is not allowed: this page only reads.")
        if word in DENIED_FUNCTIONS and _is_symbol(_at(statement, k + 1), "("):
            return SqlCheck(False, f"{t.text}() is not allowed: it runs SQL this check cannot see.")
        if t.kind in ("string", "identifier") and "://" in t.text:
            return SqlCheck(False, f"No URLs: {NO_URLS}")

    named = {t.text.lower() for t in statement if t.kind in ("word", "identifier")}
    return SqlCheck(True, tables=[table for table in tables if table.lower() in named])
