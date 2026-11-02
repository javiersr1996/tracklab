"""`tracklab publish history`: `web/public/data/history.json`, one entry per `tracklab build`
record under `<data root>/build/` (task 131), which `/engineering/history` (task 132) draws from.

It only grows. An entry already in the file is never rewritten and never dropped, even when its
record is gone from disk (the build records are not all versioned and `dbt/target` is not at all),
so the file is the history and the records are its sources. Two decisions.

1. **What a v1 record never kept comes from outside, or is "no data".** A v1 record has no dbt
   results and no contract run. Its dbt tests come from the `run_results.json` under
   `dbt/target/<step>-*` whose `generated_at` falls inside the record's own window (one per step
   or none; two is an error, not a guess). Its contracts are only the number of
   `tests/contracts/test_*.py` files at its sha (`git ls-tree`): the files were counted and never
   run. Whatever is not there is `null`, never 0: a missing dbt result is not "0 tests", and the
   page must say "no data" for it. A v2 record carries both and is copied as it is.
2. **`--check` compares the records with the file, not the file with itself.** Each record on disk
   is read again and its entry rebuilt; any difference from the entry in the file is a problem
   (a mutated duration, a step, a count). The v1 extras can vanish (a deleted `dbt/target`): when
   they are gone the entry's own value stands, when they are still there they are compared too.
   No records on disk is `PARTIAL` (a fail under `TRACKLAB_REQUIRE_FULL`, like every `--check`);
   so is a data root whose records the file has none of (the fixtures root against the published
   file), which would otherwise be a wall of false differences. Records the file lacks next to
   ones it has are a real fail: the file is behind.

Entry layout (`schema_version` 1): `id` (the record's file stem), `record_version`, `sha`,
`select` (null = complete build), `started_utc`, `finished_utc`, `wall_seconds`, `steps`
(`step_key`, `group`, `status`, `duration_ms`; `started_utc`, `finished_utc`, `dbt`,
`incremental` and `partitions` as counts, all null in a v1 except `dbt` when a `run_results.json`
matched) and `quality` (`dbt`: the step results summed and where they came from; `contracts`).
`duration_ms` is the step's own time and the `started_utc` to `finished_utc` span is wider (task
125: it includes the worker's start and close), so a chart must pick one and say which.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tracklab.build import DBT_TARGET, DBT_TEST_STATUSES, dbt_summary
from tracklab.publish.platform import RECORD_VERSIONS, load_json

SCHEMA_VERSION = 1
HISTORY_JSON = "history.json"
PIPELINE_DIR = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = "tests/contracts"
# The record's `finished_utc` is cut to the second, so the last dbt run can end "after" it.
WINDOW_SLACK = timedelta(seconds=1)
_DBT_DIR = re.compile(r"^(?P<step>.+)-[0-9a-f]{7}-[0-9a-f]{7}$")
CONTRACT_KEYS = ("executed", "status", "passed", "failed", "skipped", "errors", "duration_seconds")


def history_path(out_dir: Path) -> Path:
    return out_dir / HISTORY_JSON


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1) + "\n"


def _when(text: str) -> datetime:
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# --- what a v1 record lacks, from outside ---------------------------------------------


def dbt_runs(target: Path) -> list[tuple[str, datetime, dict[str, Any]]]:
    """Every `<target>/<step>-<run7>-<uuid7>/run_results.json`: step, `generated_at`, summary."""
    runs = []
    for path in sorted(target.glob("*/run_results.json")):
        named = _DBT_DIR.match(path.parent.name)
        if named is None:
            continue
        raw = load_json(path)
        runs.append((named["step"], _when(raw["metadata"]["generated_at"]), dbt_summary(raw)))
    return runs


def dbt_in_window(
    record: dict[str, Any], runs: list[tuple[str, datetime, dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    """Per step of the record, the dbt summary of the one run inside its window; two is an error."""
    start = _when(record["started_utc"])
    end = _when(record["finished_utc"]) + WINDOW_SLACK
    steps = {s["step_key"] for s in record["steps"]}
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for step, generated, summary in runs:
        if step in steps and start <= generated <= end:
            found[step].append(summary)
    for step, summaries in found.items():
        if len(summaries) > 1:
            raise ValueError(
                f"{len(summaries)} dbt run_results of step {step!r} fall in the window "
                f"{record['started_utc']} .. {record['finished_utc']}: cannot tell which is its own"
            )
    return {step: summaries[0] for step, summaries in found.items()}


def contract_files_at(sha: str | None, pipeline_dir: Path = PIPELINE_DIR) -> int | None:
    """`tests/contracts/test_*.py` at `sha`, counted from git; None when git or the sha or the
    folder is not there."""
    if not sha:
        return None
    try:
        done = subprocess.run(
            ["git", "ls-tree", "--name-only", sha, f"{CONTRACTS_DIR}/"],
            cwd=pipeline_dir,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if done.returncode != 0:
        return None
    names = [Path(line).name for line in done.stdout.splitlines()]
    count = sum(1 for n in names if n.startswith("test_") and n.endswith(".py"))
    return count or None


# --- the entry --------------------------------------------------------------------------


def _count(listed: Any) -> int | None:
    return len(listed) if isinstance(listed, list) else None


def _step_entry(step: dict[str, Any], dbt: dict[str, Any] | None) -> dict[str, Any]:
    partitions = step.get("partitions")
    return {
        "step_key": step["step_key"],
        "group": step["group"],
        "status": step["status"],
        "duration_ms": step["duration_ms"],
        "started_utc": step.get("started_utc"),
        "finished_utc": step.get("finished_utc"),
        "dbt": dbt,
        "incremental": step.get("incremental"),
        "partitions": (
            {key: _count(partitions.get(key)) for key in ("written", "skipped", "deleted")}
            if partitions
            else None
        ),
    }


def _dbt_total(steps: list[dict[str, Any]], source: str) -> dict[str, Any]:
    with_dbt = [s["dbt"]["tests"] for s in steps if s["dbt"]]
    if not with_dbt:
        return {"tests": None, "source": None}
    return {
        "tests": {k: sum(t.get(k, 0) for t in with_dbt) for k in DBT_TEST_STATUSES},
        "source": source,
    }


def _contracts(record: dict[str, Any], files_at_sha: int | None) -> dict[str, Any]:
    block = record.get("contracts")
    if block is None:
        return {"files": files_at_sha, **dict.fromkeys(CONTRACT_KEYS)}
    return {"files": block["files"], **{k: block.get(k) for k in CONTRACT_KEYS}}


def entry_from_record(
    record: dict[str, Any],
    record_id: str,
    *,
    dbt_by_step: dict[str, dict[str, Any]],
    contract_files: int | None,
) -> dict[str, Any]:
    """`dbt_by_step` and `contract_files` only count for a v1 record; a v2 carries its own."""
    version = record.get("schema_version", 1)
    steps = [
        _step_entry(s, s.get("dbt") if version >= 2 else dbt_by_step.get(s["step_key"]))
        for s in record["steps"]
    ]
    return {
        "id": record_id,
        "record_version": version,
        "sha": record.get("git_sha"),
        "select": record.get("select"),
        "started_utc": record["started_utc"],
        "finished_utc": record["finished_utc"],
        "wall_seconds": record["wall_seconds"],
        "steps": steps,
        "quality": {
            "dbt": _dbt_total(steps, "record" if version >= 2 else "run_results"),
            "contracts": _contracts(record, contract_files),
        },
    }


def _record_files(record_dir: Path) -> list[Path]:
    return sorted(record_dir.glob("*.json"))


def _external(
    record: dict[str, Any],
    runs: list[tuple[str, datetime, dict[str, Any]]],
    pipeline_dir: Path,
) -> tuple[dict[str, dict[str, Any]], int | None]:
    if record.get("schema_version", 1) >= 2:
        return {}, None
    return dbt_in_window(record, runs), contract_files_at(record.get("git_sha"), pipeline_dir)


def _differences(path: str, expected: Any, found: Any) -> list[str]:
    if isinstance(expected, dict) and isinstance(found, dict):
        out: list[str] = []
        for key in sorted(expected.keys() | found.keys()):
            out += _differences(f"{path}.{key}", expected.get(key), found.get(key))
        return out
    if isinstance(expected, list) and isinstance(found, list) and len(expected) == len(found):
        out = []
        for i, (a, b) in enumerate(zip(expected, found, strict=True)):
            label = a.get("step_key", i) if isinstance(a, dict) else i
            out += _differences(f"{path}[{label}]", a, b)
        return out
    return [] if expected == found else [f"{path}: record {expected!r}, file {found!r}"]


def _load_entries(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = load_json(path)["entries"]
    return entries


def run_publish_history(
    *,
    record_dir: Path,
    out_dir: Path,
    check: bool = False,
    dbt_target: Path = DBT_TARGET,
    pipeline_dir: Path = PIPELINE_DIR,
) -> int:
    target = history_path(out_dir)
    records = _record_files(record_dir)
    existing = _load_entries(target)
    known = {e["id"]: e for e in existing}
    if check and not records:
        print(
            f"publish history --check: PARTIAL: no build record under {record_dir}, "
            "nothing to compare"
        )
        return 0
    runs = dbt_runs(dbt_target)

    added: list[dict[str, Any]] = []
    problems: list[str] = []
    present = 0
    for path in records:
        record = load_json(path)
        version = record.get("schema_version", 1)
        if version not in RECORD_VERSIONS:
            print(f"publish history: record {path.name} has schema_version {version}")
            return 1
        record_id = path.stem
        if record_id in known and not check:
            continue
        old = known.get(record_id)
        try:
            dbt_by_step, files = _external(record, runs, pipeline_dir)
        except ValueError as error:
            print(f"publish history: record {path.name}: {error}")
            return 1
        if old is not None:
            # Whatever a v1 record's outside sources no longer give, the entry already kept.
            kept = {s["step_key"]: s["dbt"] for s in old["steps"] if s["dbt"]}
            dbt_by_step = {**kept, **dbt_by_step}
            files = files if files is not None else old["quality"]["contracts"]["files"]
        entry = entry_from_record(record, record_id, dbt_by_step=dbt_by_step, contract_files=files)
        if old is None:
            added.append(entry)
            continue
        present += 1
        problems += _differences(record_id, entry, old)

    if check:
        if not present and existing and added:
            print(
                f"publish history --check: PARTIAL: none of the {len(records)} records under "
                f"{record_dir} is in {target.name} (another data root?), nothing to compare"
            )
            return 0
        problems += [f"{e['id']}: record on disk, not in {target.name}" for e in added]
        ids = [e["id"] for e in existing]
        if ids != sorted(set(ids)):
            problems.append("entries are not unique and in order by id")
        if not target.is_file():
            print(f"publish history --check: {target} missing")
            return 1
        if problems:
            detail = "\n  ".join(problems)
            print(f"publish history --check: {target} differs, {len(problems)} row(s):\n  {detail}")
            return 1
        print(
            f"publish history --check: {target} matches "
            f"({present} records, {len(existing)} entries)"
        )
        return 0

    entries = sorted([*existing, *added], key=lambda e: e["id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render({"schema_version": SCHEMA_VERSION, "entries": entries}),
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"publish history: {len(entries)} entries ({len(added)} new, {len(existing)} kept), "
        f"{target} ({target.stat().st_size} bytes)"
    )
    return 0
