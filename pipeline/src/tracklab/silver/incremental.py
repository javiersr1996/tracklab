"""The incremental silver build (P16): what each match's partitions of `frames` and `events`
depend on, as one sha256 per match (task 126).

A match's fingerprint changes when anything that can change the bytes of its partitions, or the
verdict of the dbt tests over them, changes. Three layers, each folded into the next:

- **global**: the engine (`duckdb`, `dbt-core`, `dbt-adapters`, `dbt-duckdb`: a new writer can
  write other bytes from the same rows), the dbt project silver runs (`dbt_project.yml`,
  `profiles.yml` and every file under `models/`, `macros/`, `seeds/` and `tests/`, gold's models
  aside: they are the gold step's), the dbt plugin `profiles.yml` loads into the connection
  (`silver/dbt_plugin.py`), and the inputs no sport owns: `bronze/common/*`, the report CSVs and
  the ingest manifest silver reads. A change here changes every match.
- **season**, per sport: the files of a bronze table silver reads that are not one match's
  (`bronze/<sport>/<table>/data.parquet`). A change here changes every match of that sport.
- **match**: the files `bronze/<sport>/<table>/<native_match_id>.parquet` of the tables silver
  reads. A change here changes that match only.

Which tables silver reads is not a list kept by hand: it is every dbt source a silver model
depends on, from the manifest dagster-dbt already parses (`silver_sources`), so a model that starts
reading a table brings it into the fingerprint. A source of a family this module does not know
fails instead of being left out.

Bronze is hashed by its bytes, not by the `tracklab.source_sha256` it carries: bronze writes the
same raw into the same bytes (`test_two_runs_write_the_same_bytes` in the bronze tracking tests),
and the bytes are what dbt reads. The Python that writes the season inputs (the orientation probe)
needs no place here: its output is hashed, whatever wrote it. `silver/possessions.py` is a probe
dbt never imports.

The plan (task 127) compares the fingerprints with the state the last successful run of the whole
step left in `<data root>/state/silver.json` (never under `build/`, where every `*.json` is read
as a build record) and picks one of three modes:

- **skip**: no match changed, none left bronze, every output is on disk. dbt is not launched, so
  its tests do not run either, and the record says so with the reason.
- **incremental**: some matches changed (their fingerprint, or a partition the state says they
  had is gone). Their partitions and those of matches that left bronze are removed, and dbt runs
  with `silver_matches`: the dims whole, `frames` and `events` for those matches only.
- **full**: everything is rebuilt, without the var, after removing every partition. For
  `--full`, `TRACKLAB_REQUIRE_FULL`, a subset of the step, no usable state, an output missing,
  a partition with no match key, every match changed, or matches that left bronze while none
  changed (the dims must follow, and a filter that keeps no match would make dbt-duckdb write a
  row of NULLs as a partition of its own).

Before dbt, the state forgets the matches about to be rewritten (all of them in full mode); it
gains fingerprints only after dbt succeeds. A failed run therefore rebuilds them next time, even
if the old bronze has been put back in between.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any

import duckdb

ENGINE_PACKAGES = ("duckdb", "dbt-core", "dbt-adapters", "dbt-duckdb")
DBT_PROJECT_FILES = ("dbt_project.yml", "profiles.yml")
DBT_PROJECT_DIRS = ("models", "macros", "seeds", "tests")
NOT_SILVER = ("models/gold/",)  # the gold step's models
ABSENT = "absent"
_CHUNK = 1 << 20


def engine_versions() -> dict[str, str]:
    return {name: version(name) for name in ENGINE_PACKAGES}


def silver_sources(dbt_manifest: Mapping[str, Any]) -> list[tuple[str, str]]:
    """(source name, table) of every dbt source a silver model reads (every model not tagged
    gold), from dbt's parsed manifest."""
    return _sources(dbt_manifest, gold=False)


def gold_sources(dbt_manifest: Mapping[str, Any]) -> list[tuple[str, str]]:
    """(source name, table) of every dbt source a gold model reads. A gold model that reads
    anything else outside gold (a silver model, a seed) fails: the gold fingerprint does not
    cover it, and a skip would then hide a change."""
    return _sources(dbt_manifest, gold=True)


def _sources(dbt_manifest: Mapping[str, Any], *, gold: bool) -> list[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for node in dbt_manifest["nodes"].values():
        if node["resource_type"] != "model" or ("gold" in node.get("tags", [])) != gold:
            continue
        for upstream in node["depends_on"]["nodes"]:
            if upstream.startswith("source."):
                source = dbt_manifest["sources"][upstream]
                found.add((source["source_name"], source["name"]))
            elif gold and "gold" not in dbt_manifest["nodes"][upstream].get("tags", []):
                raise ValueError(f"gold model {node['name']} reads {upstream}, outside gold")
    return sorted(found)


@dataclass(frozen=True)
class Inputs:
    """Where silver's inputs live: the paths `assets_dbt.silver` hands dbt."""

    data_dir: Path
    reports_dir: Path
    manifest_dir: Path
    dbt_dir: Path
    plugin: Path
    engine: Mapping[str, str] = field(default_factory=engine_versions)


@dataclass(frozen=True)
class Fingerprints:
    global_digest: str
    season: dict[str, str]  # sport -> digest, the global one folded in
    matches: dict[str, str]  # "<sport>/<native_match_id>" -> digest, its sport's season folded in


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(parts: Iterable[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for label, value in parts:
        digest.update(f"{label}\0{value}\n".encode())
    return digest.hexdigest()


def _file_part(label: str, path: Path) -> tuple[str, str]:
    return label, sha256_file(path) if path.is_file() else ABSENT


def _dbt_project_parts(dbt_dir: Path) -> list[tuple[str, str]]:
    paths = [dbt_dir / name for name in DBT_PROJECT_FILES]
    for folder in DBT_PROJECT_DIRS:
        paths += sorted(p for p in (dbt_dir / folder).rglob("*") if p.is_file())
    parts = []
    for path in paths:
        label = path.relative_to(dbt_dir).as_posix()
        if not label.startswith(NOT_SILVER):
            parts.append(_file_part(f"dbt/{label}", path))
    return parts


def match_key(sport: str, native_match_id: int) -> str:
    return f"{sport}/{native_match_id}"


def fingerprints(sources: Sequence[tuple[str, str]], inputs: Inputs) -> Fingerprints:
    """One digest per match that has a file in a per-match bronze table silver reads."""
    shared: list[tuple[str, str]] = []
    sport_wide: dict[str, list[tuple[str, str]]] = {}
    per_match: dict[str, list[tuple[str, str]]] = {}
    for source, table in sources:
        if source == "bronze_common":
            folder = inputs.data_dir / "bronze" / "common" / table
            shared += [_file_part(f"bronze/common/{table}/{p.name}", p) for p in _parquet(folder)]
        elif source.startswith("bronze_"):
            sport = source.removeprefix("bronze_")
            sport_wide.setdefault(sport, [])
            for path in _parquet(inputs.data_dir / "bronze" / sport / table):
                part = _file_part(f"bronze/{sport}/{table}/{path.name}", path)
                if path.stem.isdigit():
                    per_match.setdefault(match_key(sport, int(path.stem)), []).append(part)
                else:
                    sport_wide[sport].append(part)
        elif source == "reports":
            shared.append(_file_part(f"reports/{table}.csv", inputs.reports_dir / f"{table}.csv"))
        elif source == "manifest":
            shared.append(
                _file_part(f"manifest/{table}.json", inputs.manifest_dir / f"{table}.json")
            )
        else:
            raise ValueError(
                f"silver reads dbt source {source!r}, which the fingerprint does not know"
            )
    global_digest = _digest(
        [
            *((f"engine/{name}", inputs.engine[name]) for name in ENGINE_PACKAGES),
            *_dbt_project_parts(inputs.dbt_dir),
            _file_part("plugin", inputs.plugin),
            *shared,
        ]
    )
    season = {
        sport: _digest([("global", global_digest), *sorted(parts)])
        for sport, parts in sorted(sport_wide.items())
    }
    matches = {
        key: _digest([("season", season[key.split("/")[0]]), *sorted(parts)])
        for key, parts in sorted(per_match.items())
    }
    return Fingerprints(global_digest, season, matches)


def _parquet(folder: Path) -> list[Path]:
    """What dbt's sources read from a bronze table folder: every `*.parquet` in it."""
    return sorted(folder.glob("*.parquet"))


# --- the plan and the state (task 127) ---------------------------------------------

PARTITIONED = ("events", "frames")
DBT_VAR = "silver_matches"
DATABASE = "tracklab.duckdb"  # profiles.yml: `<data root>/tracklab.duckdb`
STATE_VERSION = 1
FULL_ENV = "TRACKLAB_BUILD_FULL"  # `tracklab build --full`, read in the step's own process
PLAN_METADATA_KEY = "tracklab/incremental"  # the step's observation; build.py reads it
NO_KEY = "__HIVE_DEFAULT_PARTITION__"  # DuckDB's name for a partition value that is NULL


@dataclass(frozen=True)
class Plan:
    mode: str  # "skip", "incremental" or "full"
    reason: str
    written: list[str]  # matches whose partitions dbt rewrites
    skipped: list[str]  # matches whose partitions stay as they are
    deleted: list[str]  # matches that left bronze: their partitions are removed

    def dbt_vars(self) -> dict[str, Any]:
        """The var `frames` and `events` filter bronze by; none (every match) unless incremental."""
        if self.mode != "incremental":
            return {}
        ids: dict[str, list[int]] = {}
        for key in self.written:
            sport, native = key.split("/")
            ids.setdefault(sport, []).append(int(native))
        return {DBT_VAR: ids}

    def record(self) -> dict[str, Any]:
        return asdict(self)


def external_models(dbt_manifest: Mapping[str, Any], *, gold: bool = False) -> list[str]:
    """The silver (or gold) models that write files (`materialized: external`): their folder
    under `silver/` (`gold/`) must hold Parquet for a skip to be honest."""
    return sorted(
        node["name"]
        for node in dbt_manifest["nodes"].values()
        if node["resource_type"] == "model"
        and ("gold" in node.get("tags", [])) == gold
        and node["config"].get("materialized") == "external"
    )


def full_reason(
    *, full: bool, require_full: bool, whole_step: bool, step: str = "silver"
) -> str | None:
    if full:
        return "--full"
    if require_full:
        return "TRACKLAB_REQUIRE_FULL is set"
    if not whole_step:
        return f"a subset of the {step} step was selected"
    return None


def state_path(data_dir: Path, step: str = "silver") -> Path:
    return data_dir / "state" / f"{step}.json"


def read_state(data_dir: Path, step: str = "silver") -> dict[str, Any] | None:
    """The last successful run's state; None when there is none or it cannot be trusted."""
    try:
        state = json.loads(state_path(data_dir, step).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        return None
    return state


def write_state(data_dir: Path, state: Mapping[str, Any], step: str = "silver") -> None:
    """Atomically (a temporary file renamed over the old one), with LF."""
    path = state_path(data_dir, step)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(state, indent=2, sort_keys=True) + "\n"
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def partition_dir(silver_dir: Path, model: str, key: str) -> Path:
    sport, native = key.split("/")
    return silver_dir / model / f"sport={sport}" / f"native_match_id={native}"


def partitions_on_disk(silver_dir: Path) -> dict[str, set[str]]:
    """Match key -> the partitioned models holding Parquet for it. A partition written with no
    match key is listed under `NO_KEY`."""
    found: dict[str, set[str]] = {}
    for model in PARTITIONED:
        for folder in (silver_dir / model).glob("sport=*/native_match_id=*"):
            if not any(folder.glob("*.parquet")):
                continue
            sport = folder.parent.name.removeprefix("sport=")
            native = folder.name.removeprefix("native_match_id=")
            key = match_key(sport, int(native)) if native.isdigit() and sport != NO_KEY else NO_KEY
            found.setdefault(key, set()).add(model)
    return found


def _present(path: Path) -> bool:
    return path.is_file() if path.suffix == ".duckdb" else any(path.rglob("*.parquet"))


def _stale(
    key: str, fp: Fingerprints, known: Mapping[str, Any], disk: Mapping[str, set[str]]
) -> bool:
    entry = known.get(key)
    if entry is None or entry["fingerprint"] != fp.matches[key]:
        return True
    return any(model not in disk.get(key, set()) for model in entry["partitions"])


def _why_all(fp: Fingerprints, state: Mapping[str, Any]) -> str:
    if state.get("global") != fp.global_digest:
        return "a global input changed: engine, dbt project, plugin or an input no sport owns"
    sports = sorted(s for s, d in fp.season.items() if state.get("season", {}).get(s) != d)
    if sports:
        return f"season tables changed: {', '.join(sports)}"
    return "the bronze of every match changed"


def make_plan(
    fp: Fingerprints,
    state: Mapping[str, Any] | None,
    data_dir: Path,
    models: Sequence[str],
    forced: str | None,
) -> Plan:
    """What the step does, from the fingerprints, the state and what is on disk. `models` are
    the silver models that write files; `forced` is `full_reason`'s answer."""
    silver = data_dir / "silver"
    current = sorted(fp.matches)
    disk = partitions_on_disk(silver)
    known: Mapping[str, Any] = state["matches"] if state else {}
    deleted = sorted((set(disk) | set(known)) - set(current) - {NO_KEY})
    outputs = (data_dir / DATABASE, *(silver / model for model in models))
    missing = [path.name for path in outputs if not _present(path)]
    reason = forced
    if reason is None and state is None:
        reason = "no state left by a successful run of the whole step"
    elif reason is None and missing:
        reason = f"silver output missing: {', '.join(missing)}"
    elif reason is None and NO_KEY in disk:
        reason = "a partition with no match key is on disk"
    if reason is not None or state is None:
        return Plan("full", reason or "", current, [], deleted)
    changed = [key for key in current if _stale(key, fp, known, disk)]
    if not changed and not deleted:
        return Plan("skip", f"no input changed since run {state['run_id']}", [], current, [])
    if not changed:
        reason = f"{len(deleted)} match(es) left bronze and none changed"
        return Plan("full", reason, current, [], deleted)
    if len(changed) == len(current):
        return Plan("full", f"every match changed ({_why_all(fp, state)})", current, [], deleted)
    unchanged = sorted(set(current) - set(changed))
    reason = f"{len(changed)} of {len(current)} matches changed"
    return Plan("incremental", reason, changed, unchanged, deleted)


def prepare(
    plan: Plan, state: Mapping[str, Any] | None, data_dir: Path, models: Sequence[str]
) -> None:
    """Before dbt: the state forgets what is about to be rewritten, then its partitions go.
    `models` are the partitioned models this run builds."""
    if plan.mode == "full" or state is None:
        state_path(data_dir).unlink(missing_ok=True)
    else:
        gone = {*plan.written, *plan.deleted}
        kept = {k: v for k, v in state["matches"].items() if k not in gone}
        write_state(data_dir, {**state, "matches": kept})
    silver = data_dir / "silver"
    for model in models:
        root = silver / model
        if plan.mode == "full":
            targets = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
        else:
            targets = [partition_dir(silver, model, key) for key in (*plan.written, *plan.deleted)]
        for target in targets:
            if target.exists():
                shutil.rmtree(target)


def _drop_null_key_partitions(root: Path, model: str) -> None:
    """dbt-duckdb writes one NULL row under `__HIVE_DEFAULT_PARTITION__` when a partitioned
    model returns no row, which happens when the only match rebuilt has no frames or events.
    That lone row is no data: drop it, so the model simply has no partition for the match.
    Several rows under a NULL key are real data the view would hide, so those still raise."""
    for folder in (
        *root.glob(f"sport={NO_KEY}"),
        *root.glob(f"sport=[!_]*/native_match_id={NO_KEY}"),
    ):
        files = [str(p) for p in folder.rglob("*.parquet")]
        rows = 0
        if files:
            with duckdb.connect() as con:
                rows = con.execute("SELECT count(*) FROM read_parquet(?)", [files]).fetchone()[0]  # type: ignore[index]
        if rows > 1:
            raise RuntimeError(
                f"silver {model}: dbt wrote {rows} rows with no match key, which the view over "
                "it hides; rebuild with `tracklab build --full`"
            )
        shutil.rmtree(folder)
        if folder.parent != root and not any(folder.parent.iterdir()):
            folder.parent.rmdir()


def finish(fp: Fingerprints, data_dir: Path, run_id: str, *, whole_step: bool) -> None:
    """After dbt succeeded: drop the lone NULL row dbt writes for an empty model (several rows
    with no match key raise), then remember what was built
    (only when the whole step ran: a subset leaves no state behind)."""
    silver = data_dir / "silver"
    for model in PARTITIONED:
        _drop_null_key_partitions(silver / model, model)
    if not whole_step:
        return
    disk = partitions_on_disk(silver)
    matches = {
        key: {"fingerprint": digest, "partitions": sorted(disk.get(key, set()))}
        for key, digest in fp.matches.items()
    }
    state = {
        "version": STATE_VERSION,
        "run_id": run_id,
        "global": fp.global_digest,
        "season": fp.season,
        "matches": matches,
    }
    write_state(data_dir, state)


# --- gold (task 129) ---------------------------------------------------------------
#
# Gold has no match grain: its six aggregates read the season tables of bronze and the four
# dimensional models read those six. So the step has one fingerprint and two modes: skip (it
# is unchanged, every output is on disk) or full. The fingerprint folds in what can change
# gold's bytes or the verdict of its tests, in four groups the state keeps apart so the
# reason can say which moved:
#
# - `bronze`: every `*.parquet` of each table a gold model reads (`gold_sources`);
# - `dbt`: `dbt_project.yml`, `profiles.yml`, the macros, gold's models and `schema.yml`, the
#   source definitions and the singular tests (silver's models and seeds are not gold's);
# - `plugin`: `silver/dbt_plugin.py`, which loads into the connection;
# - `engine`: the versions of `duckdb`, `dbt-core`, `dbt-adapters` and `dbt-duckdb`.
#
# The state (`<data root>/state/gold.json`) is forgotten before dbt and written only after it
# succeeds, as silver's is.

GOLD = "gold"
GOLD_DBT_DIRS = ("macros", "models/gold", "models/sources", "tests")


@dataclass(frozen=True)
class GoldFingerprint:
    digest: str
    groups: dict[str, str]  # bronze, dbt, plugin, engine


def gold_fingerprint(sources: Sequence[tuple[str, str]], inputs: Inputs) -> GoldFingerprint:
    bronze: list[tuple[str, str]] = []
    for source, table in sources:
        if not source.startswith("bronze_") or source == "bronze_common":
            raise ValueError(
                f"gold reads dbt source {source!r}, which the fingerprint does not know"
            )
        sport = source.removeprefix("bronze_")
        for path in _parquet(inputs.data_dir / "bronze" / sport / table):
            bronze.append(_file_part(f"bronze/{sport}/{table}/{path.name}", path))
    dbt = [_file_part(f"dbt/{name}", inputs.dbt_dir / name) for name in DBT_PROJECT_FILES]
    for folder in GOLD_DBT_DIRS:
        for path in sorted(p for p in (inputs.dbt_dir / folder).rglob("*") if p.is_file()):
            dbt.append(_file_part(f"dbt/{path.relative_to(inputs.dbt_dir).as_posix()}", path))
    groups = {
        "bronze": _digest(sorted(bronze)),
        "dbt": _digest(dbt),
        "plugin": _digest([_file_part("plugin", inputs.plugin)]),
        "engine": _digest((name, inputs.engine[name]) for name in ENGINE_PACKAGES),
    }
    return GoldFingerprint(_digest(sorted(groups.items())), groups)


def make_gold_plan(
    fp: GoldFingerprint,
    state: Mapping[str, Any] | None,
    data_dir: Path,
    models: Sequence[str],
    forced: str | None,
) -> Plan:
    """skip or full, from the fingerprint, the state and what is on disk. `models` are the gold
    models that write files; `forced` is `full_reason`'s answer."""
    missing = [m for m in models if not any((data_dir / GOLD / m).rglob("*.parquet"))]
    reason = forced
    if reason is None and state is None:
        reason = "no state left by a successful run of the whole step"
    elif reason is None and missing:
        reason = f"gold output missing: {', '.join(missing)}"
    elif reason is None and state is not None and state["digest"] != fp.digest:
        moved = [g for g, d in fp.groups.items() if state["groups"].get(g) != d]
        reason = f"gold inputs changed: {', '.join(moved)}"
    if reason is not None or state is None:
        return Plan("full", reason or "", [], [], [])
    return Plan("skip", f"no input changed since run {state['run_id']}", [], [], [])


def forget_gold(data_dir: Path) -> None:
    """Before dbt: the old state goes, so a failed run is rebuilt next time."""
    state_path(data_dir, GOLD).unlink(missing_ok=True)


def finish_gold(fp: GoldFingerprint, data_dir: Path, run_id: str, *, whole_step: bool) -> None:
    """After dbt succeeded: remember what was built (only when the whole step ran)."""
    if whole_step:
        state = {
            "version": STATE_VERSION,
            "run_id": run_id,
            "digest": fp.digest,
            "groups": fp.groups,
        }
        write_state(data_dir, state, GOLD)
