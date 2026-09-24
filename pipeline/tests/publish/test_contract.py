"""The 12 published possessions against `web/lib/replay/schema.json`.

Skipped when the real bundle has not been built and published (CI has no real
data, same as `tests/contracts`): this is the pytest half of task 17's
acceptance, `uv run pytest tests/publish -q` printing `12/12 valid`. The
schema file itself is the one `web/lib/replay/schema.ts` re-exports, so this
is also the only place a mismatch between the two would show.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

PIPELINE = Path(__file__).resolve().parents[2]
REPO_ROOT = PIPELINE.parent
SCHEMA_PATH = REPO_ROOT / "web" / "lib" / "replay" / "schema.json"
DATA_DIR = REPO_ROOT / "web" / "public" / "data"
POSSESSIONS_DIR = DATA_DIR / "possessions"
MAX_BYTES = 300_000
N_EXPECTED = 12

pytestmark = pytest.mark.skipif(
    not POSSESSIONS_DIR.is_dir() or not any(POSSESSIONS_DIR.glob("*.json")),
    reason="web/public/data/possessions not built; run `tracklab publish possessions`",
)


def _schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema


def test_schema_itself_is_a_valid_draft_2020_12_schema() -> None:
    Draft202012Validator.check_schema(_schema())


def test_every_published_possession_validates_against_the_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    validator = Draft202012Validator(_schema())
    files = sorted(POSSESSIONS_DIR.glob("*.json"))

    ok = 0
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        errors = list(validator.iter_errors(payload))
        if errors:
            for error in errors[:5]:
                print(f"{path.name}: {error.message} at {list(error.path)}")
        else:
            ok += 1

    with capsys.disabled():
        print(f"{ok}/{len(files)} valid")

    assert len(files) == N_EXPECTED
    assert ok == len(files)


def test_every_file_is_under_the_300kb_cap() -> None:
    files = sorted(POSSESSIONS_DIR.glob("*.json"))
    sizes = {f.name: f.stat().st_size for f in files}
    for name, size in sizes.items():
        print(f"{name}: {size} bytes")
    assert len(sizes) == N_EXPECTED
    assert all(size < MAX_BYTES for size in sizes.values())


def test_files_are_written_with_lf_line_endings_only() -> None:
    """`Path.write_text` on Windows translates `\\n` to `\\r\\n` unless told
    not to (task 17's own lesson): a CRLF byte anywhere would prove that."""
    files = list(POSSESSIONS_DIR.glob("*.json")) + [DATA_DIR / "index.json"]
    offenders = [f.name for f in files if b"\r" in f.read_bytes()]
    assert offenders == []


def test_index_lists_exactly_the_published_files() -> None:
    index = json.loads((DATA_DIR / "index.json").read_text(encoding="utf-8"))
    assert index["schema_version"] == 1
    listed = {entry["file"] for entry in index["possessions"]}
    on_disk = {f"possessions/{p.name}" for p in POSSESSIONS_DIR.glob("*.json")}
    assert listed == on_disk
    assert len(index["possessions"]) == N_EXPECTED


def test_at_least_four_matches_per_sport() -> None:
    """The plan's own floor: 6 possessions per sport from at least 4 distinct
    matches, so the bundle does not lean on one or two matches."""
    index = json.loads((DATA_DIR / "index.json").read_text(encoding="utf-8"))
    by_sport: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    for entry in index["possessions"]:
        by_sport.setdefault(entry["sport"], set()).add(entry["match_id"])
        counts[entry["sport"]] = counts.get(entry["sport"], 0) + 1
    print({sport: sorted(matches) for sport, matches in by_sport.items()})
    assert counts == {"basketball": 6, "football": 6}
    assert all(len(matches) >= 4 for matches in by_sport.values())


def test_frames_are_consecutive_at_the_native_rate() -> None:
    """The replay engine interpolates between consecutive samples and never looks at
    the time between them, so a hole in a published possession would be drawn as a
    slide. The selection admits up to 10% missing frames; none may be a hole."""
    for path in sorted(POSSESSIONS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        step = 1000 // payload["sample_rate_hz"]
        times = [frame["t"] for frame in payload["frames"]]
        gaps = {b - a for a, b in zip(times, times[1:], strict=False)}
        assert gaps == {step}, f"{path.name}: steps {sorted(gaps)}, expected {step}"
