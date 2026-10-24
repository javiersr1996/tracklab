"""/learn stays clear of the Analytics Cup until it is over (task 75, fence V1 to V7).

`web/lib/learn/fence.json` holds the fence: its date, whether Javier lifted it, the ten match ids
ac2 keeps held out and the key names of the layers it studies. The test reads every file /learn can
publish (the JSON under `web/public/data/learn/` and the text of `pipeline/src/tracklab/learn/`) and
fails on a forbidden key or a held-out id. What a lesson says in prose is the reviewer's, not this
test's. It prints how many files it saw and fails on none: a test over zero files passes by
construction.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
FENCE = json.loads((REPO / "web" / "lib" / "learn" / "fence.json").read_text("utf-8"))
JSON_DIR = REPO / "web" / "public" / "data" / "learn"
SRC_DIR = REPO / "pipeline" / "src" / "tracklab" / "learn"


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
    sources = sorted(p for p in SRC_DIR.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
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


def test_the_fence_is_not_lifted_before_its_date() -> None:
    assert not FENCE["lifted"] or date.today() >= date.fromisoformat(FENCE["until"])


def test_no_learn_file_crosses_the_fence() -> None:
    seen, problems = learn_problems()
    print(f"learn fence: {seen} files seen")
    assert seen > 0, "the fence looked at no file, so it protects nothing"
    assert problems == []
