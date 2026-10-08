"""Shared by every test under tests/: nothing a build record or a published JSON
carries may name this machine (tasks 32 and 34). That is `source_path` (the
receipt's outside clone), the host name, the home directory and any drive path,
and, since task 44, a database connection string (URI or key=value form).
"""

from __future__ import annotations

import platform
import re
from collections.abc import Callable
from pathlib import Path

import pytest

_DRIVE = re.compile(r"\b[A-Za-z]:[\\/]")
_DSN = re.compile(r"postgres(?:ql)?://|\b(?:host|hostaddr|password|user|dbname)\s*=", re.IGNORECASE)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (*_strings(k), *_strings(v))]
    if isinstance(value, list | tuple):
        return [s for item in value for s in _strings(item)]
    return []


def local_traces(payload: object) -> list[str]:
    """Every key or string value of `payload` that names this machine."""
    home = Path.home()
    forbidden = [
        f
        for f in ("source_path", platform.node(), str(home), home.as_posix(), "/home/", "/Users/")
        if f
    ]
    return [
        s
        for s in _strings(payload)
        if any(f in s for f in forbidden) or _DRIVE.search(s) or _DSN.search(s)
    ]


@pytest.fixture
def assert_no_local_traces() -> Callable[[object], None]:
    def check(payload: object) -> None:
        assert local_traces(payload) == []

    return check
