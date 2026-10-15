"""`fmt`: a byte count as the short, human string `tracklab publish platform`'s
title is built from (task 34) -- base 10 (1000), one decimal once it leaves
bytes, `B`/`KB`/`MB`/`GB`/`TB`. Its own module because task 35's TypeScript
`formatBytes` is asked to match it case for case, and a function shared
between two languages is one each can import or port without the rest of
`platform.py` coming along.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_UNITS = ("B", "KB", "MB", "GB", "TB")


def _one_decimal(value: float) -> Decimal:
    """`value` to one decimal, a tie rounded up: what JavaScript's `toFixed(1)`
    does, where Python's own `f"{1.25:.1f}"` rounds to even ("1.2")."""
    return Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def fmt(n: int) -> str:
    """`fmt(999) == "999 B"`, `fmt(1230786) == "1.2 MB"`,
    `fmt(2316182304) == "2.3 GB"`: base 10, so this disagrees with a base-1024
    reading past the first unit. The unit is chosen on the rounded value, so
    `fmt(999_950)` is "1.0 MB", never "1000.0 KB"."""
    if n < 1000:
        return f"{n} B"
    value = float(n)
    unit = 0
    while _one_decimal(value) >= 1000 and unit < len(_UNITS) - 1:
        value /= 1000.0
        unit += 1
    return f"{_one_decimal(value)} {_UNITS[unit]}"
