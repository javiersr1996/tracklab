"""/learn stays clear of the Analytics Cup until it is over (task 75, fence V1 to V7).

`web/lib/learn/fence.json` holds the fence: its date, whether Javier lifted it, the ten match ids
ac2 keeps held out and the key names of the layers it studies. The test reads every file /learn can
publish (the JSON under `web/public/data/learn/` and the text of `pipeline/src/tracklab/learn/`) and
fails on a forbidden key or a held-out id. What a lesson says in prose is the reviewer's, not this
test's. It prints how many files it saw and fails on none: a test over zero files passes by
construction.

P9 (task 84) adds the probes of `pipeline/scripts/probe_learn_*.py` to the text it reads, and a
second test: no code of /learn names a team-shape column of `phases_of_play` (V5:
`team_in_possession_width_start` and its seven siblings). The pitch's own dimensions
(`pitch_length`, `pitch_width`, lesson 3) are not team shape and do not match.

P11 (task 99) adds /sql: the files of `pipeline/src/tracklab/sqlcourse/` and the
`web/public/data/sql/course.json` they build. A held-out id fails anywhere in them, a forbidden key
anywhere in a `.sql` file (header, query, comment) and in the keys and values of course.json, and
the course's code is read by the team-shape test like the code of /learn.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
FENCE = json.loads((REPO / "web" / "lib" / "learn" / "fence.json").read_text("utf-8"))
JSON_DIR = REPO / "web" / "public" / "data" / "learn"
SRC_DIR = REPO / "pipeline" / "src" / "tracklab" / "learn"
PROBES = sorted((REPO / "pipeline" / "scripts").glob("probe_learn_*.py"))
SQL_DIR = REPO / "pipeline" / "src" / "tracklab" / "sqlcourse"
SQL_JSON = REPO / "web" / "public" / "data" / "sql" / "course.json"
CODE_DIRS = [
    SRC_DIR,
    REPO / "web" / "lib" / "learn",
    REPO / "web" / "components" / "learn",
    REPO / "web" / "app" / "learn",
    SQL_DIR,
]
TEAM_SHAPE = re.compile(r"possession_(?:width|length)|_(?:width|length)_")


def _walk(value: Any) -> tuple[list[str], list[str]]:
    """The keys and the scalars of a JSON value, as text."""
    if isinstance(value, dict):
        keys, scalars = [str(k) for k in value], []
        for v in value.values():
            k, s = _walk(v)
            keys, scalars = keys + k, scalars + s
        return keys, scalars
    if isinstance(value, list):
        keys, scalars = [], []
        for v in value:
            k, s = _walk(v)
            keys, scalars = keys + k, scalars + s
        return keys, scalars
    return [], [str(value)]


def learn_problems() -> tuple[int, list[str]]:
    """How many files /learn can publish, and what each breaks."""
    problems: list[str] = []
    jsons = sorted(JSON_DIR.rglob("*.json")) if JSON_DIR.exists() else []
    sources = _files([SRC_DIR]) + PROBES
    for path in jsons:
        keys, scalars = _walk(json.loads(path.read_text("utf-8")))
        problems += [
            f"{path.name}: key {k!r}" for k in keys for f in FENCE["forbidden_keys"] if f in k
        ]
        problems += [
            f"{path.name}: id {h}" for h in FENCE["held_out"] for t in keys + scalars if h in t
        ]
    for path in sources:
        text = path.read_text("utf-8")
        problems += [f"{path.name}: id {h}" for h in FENCE["held_out"] if h in text]
    return len(jsons) + len(sources), problems


def sql_course_problems() -> tuple[int, list[str]]:
    """How many files /sql is built from or publishes, and what each breaks."""
    problems: list[str] = []
    sources = _files([SQL_DIR])
    for path in sources:
        text = path.read_text("utf-8")
        problems += [f"{path.name}: id {h}" for h in FENCE["held_out"] if h in text]
        if path.suffix == ".sql":
            problems += [f"{path.name}: key {k!r}" for k in FENCE["forbidden_keys"] if k in text]
    jsons = [SQL_JSON] if SQL_JSON.exists() else []
    for path in jsons:
        keys, scalars = _walk(json.loads(path.read_text("utf-8")))
        problems += [
            f"{path.name}: {t!r} names {f!r}"
            for t in keys + scalars
            for f in FENCE["forbidden_keys"] + FENCE["held_out"]
            if f in t
        ]
    return len(sources) + len(jsons), problems


def _files(dirs: list[Path]) -> list[Path]:
    return sorted(
        p for d in dirs for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts
    )


def team_shape_problems() -> tuple[int, list[str]]:
    """How many code files of /learn there are, and which name a team-shape column. The fence
    itself names them, to forbid them, and is left out."""
    files = [p for p in _files(CODE_DIRS) if p.name != "fence.json"] + PROBES
    problems = [
        f"{path.name}: {m.group(0)!r}"
        for path in files
        for m in TEAM_SHAPE.finditer(path.read_text("utf-8"))
    ]
    return len(files), problems


def test_the_fence_is_not_lifted_before_its_date() -> None:
    assert not FENCE["lifted"] or date.today() >= date.fromisoformat(FENCE["until"])


def test_no_learn_file_crosses_the_fence() -> None:
    seen, problems = learn_problems()
    print(f"learn fence: {seen} files seen")
    assert seen > 0, "the fence looked at no file, so it protects nothing"
    assert problems == []


def test_no_sql_course_file_crosses_the_fence() -> None:
    seen, problems = sql_course_problems()
    print(f"sql course fence: {seen} files seen")
    assert seen > 0, "the fence looked at no file, so it protects nothing"
    assert problems == []


def test_no_learn_code_names_a_team_shape_column() -> None:
    seen, problems = team_shape_problems()
    print(f"learn team shape: {seen} files seen")
    assert seen > 0, "the check looked at no file, so it protects nothing"
    assert problems == []
