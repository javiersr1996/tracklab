"""The fingerprint of a query's result: the one rule Python and the browser both implement.

The spec's "Normalization" (docs/superpowers/specs/2026-10-26-sql-course-design.md). DuckDB types
the values itself: the query runs inside `wrap`, whose one column is each row as JSON text. Each
number becomes the integer `sign(x) * floor(|x| * 10000 + 0.5)`, computed in IEEE doubles as
JavaScript computes it (`-0` is `0`); strings, null and booleans stay as JSON gives them; a list
or a struct is normalized inside. Unordered rows are sorted by the UTF-8 bytes of their canonical
JSON, whose object keys are themselves sorted by their UTF-8 bytes, and the hash is the SHA-256 of
the canonical JSON of all rows. `NaN`, `Infinity` and numbers with `|x| * 10000` at or above 2^53
cannot be compared: `NotComparable`.

`web/tests/fixtures/sql-normalize.json` pins the rule from wrapper text to hash, with expected
values computed by the same rule written in JavaScript; pytest and vitest both read it.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from tracklab.sqlcourse.gate import SqlSyntaxError, tokenize

SCALE = 10000
LIMIT = 2**53


class NotComparable(ValueError):
    """A value the checker cannot compare: NaN, Infinity or a number too large."""


def wrap(query: str) -> str:
    """The wrapper of the spec around a query, its trailing `;` stripped. A `;` counts as trailing
    when only whitespace, comments and more `;` follow it; the gate's tokenizer finds it, so a `;`
    in a string or a comment is left alone. The newlines keep a trailing line comment of the query
    from swallowing the closing parenthesis."""
    body = query.strip()
    try:
        tokens = tokenize(body)
    except SqlSyntaxError:
        body = body.rstrip(";")  # the gate refuses it before any run
    else:
        k = len(tokens)
        while k > 0 and tokens[k - 1].kind == "symbol" and tokens[k - 1].text == ";":
            k -= 1
        if k < len(tokens):
            body = body[: tokens[k].at]
    return f"SELECT json_array(*COLUMNS(*))::VARCHAR FROM (\n{body.rstrip()}\n) q"


def number(value: float | int) -> int:
    try:
        x = float(value)
    except OverflowError:
        raise NotComparable(str(value)) from None
    if not math.isfinite(x) or abs(x) * SCALE >= LIMIT:
        raise NotComparable(str(value))
    n = math.floor(abs(x) * SCALE + 0.5)
    return -n if x < 0 else n


def value(v: Any) -> Any:
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, int | float):
        return number(v)
    if isinstance(v, list):
        return [value(x) for x in v]
    if isinstance(v, dict):
        return {k: value(x) for k, x in v.items()}
    raise TypeError(f"not a JSON value: {v!r}")


def canonical(rows: Any) -> str:
    return json.dumps(
        rows, ensure_ascii=False, separators=(",", ":"), allow_nan=False, sort_keys=True
    )


def parse_row(text: str) -> list[Any]:
    """One row of the wrapper. Python's json reads `NaN` and `Infinity` (JavaScript's does not);
    `number` refuses them either way."""
    row = json.loads(text)
    if not isinstance(row, list):
        raise TypeError(f"a wrapper row is a JSON array, not {text!r}")
    return row


def normalize(texts: list[str], ordered: bool) -> list[list[Any]]:
    rows = [value(parse_row(t)) for t in texts]
    if not ordered:
        rows.sort(key=lambda row: canonical(row).encode("utf-8"))
    return rows


def fingerprint(texts: list[str], ordered: bool) -> tuple[str, str]:
    """The canonical JSON of the normalized rows and its SHA-256, hex."""
    text = canonical(normalize(texts, ordered))
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()
