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
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any

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
    found: set[tuple[str, str]] = set()
    for node in dbt_manifest["nodes"].values():
        if node["resource_type"] != "model" or "gold" in node.get("tags", []):
            continue
        for upstream in node["depends_on"]["nodes"]:
            if upstream.startswith("source."):
                source = dbt_manifest["sources"][upstream]
                found.add((source["source_name"], source["name"]))
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
