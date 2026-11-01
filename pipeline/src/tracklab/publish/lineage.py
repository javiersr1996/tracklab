"""`tracklab publish lineage`: the Dagster asset graph exported to
`web/public/data/lineage.json` (task 33), so `/platform` draws the real graph
instead of `dbt docs` (which only covers 22 of the 82 nodes: seeds, silver and gold).

`lineage_from_defs` reads the graph `defs` already carries (82 keys: 81
materializable assets plus `manifest_sources`, a spec no step writes) and, for
the 22 dbt-backed nodes (10 silver models, 2 seeds, 10 gold models), reads `dbt/target/
manifest.json` for their description, columns and test count -- the same file
`dbt docs generate` builds from, without the 3 MB HTML or the `generated_at`
that would break the clean clone. A dbt test's owner is `attached_node` when
dbt sets it (every generic column test); a singular test in `dbt/tests/*.sql`
has none, so it is attributed to the first model or seed it depends on, which
is consistently the one in its `FROM` clause (checked against the two singular
tests that touch two models each: `assert_frames_entities_in_dim_entity` and
`assert_one_ball_per_match`).

Every other node keeps whatever `description` its `AssetSpec` or `@asset` sets
(the quality checks set theirs in `assets_quality`). A bronze table sets none of
its own: its description is the one of its dbt source table in
`dbt/models/sources/*.yml` (`source.<project>.bronze_<sport>.<table>` in the
manifest), so the prose lives in one place and the page reads it from here.
`undescribed` lists the nodes left without one and both `--check` and the
publish refuse to go on while it is not empty (task 123).

The output is ordered by key and edge, `indent=2`, no timestamps: the whole
point is that two runs produce the same bytes, byte for byte, so CI's
`--check` can compare it against the versioned file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dagster import Definitions

SCHEMA_VERSION = 1
GROUPS_IN_FLOW = ("ingest", "bronze", "silver", "gold", "quality", "publish", "runs", "pose")
DBT_MANIFEST = Path("dbt/target/manifest.json")
SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "bronze" / "schemas"
LINEAGE_JSON = "lineage.json"


@dataclass(frozen=True)
class DbtNode:
    description: str
    columns: list[str]
    tests: int


def _test_owner(uid: str, node: dict[str, Any]) -> str:
    """The model or seed a dbt test is attributed to: `attached_node` when dbt
    sets it (every generic column test), else the first model/seed the test's
    own SQL depends on (a singular test), which is its `FROM` table."""
    attached = node.get("attached_node")
    if attached:
        return str(attached)
    for dep in node.get("depends_on", {}).get("nodes", []):
        if dep.split(".")[0] in ("model", "seed"):
            return str(dep)
    raise ValueError(f"dbt test {uid} depends on no model or seed to attribute it to")


def dbt_nodes(manifest: dict[str, Any]) -> dict[str, DbtNode]:
    """Every model and seed of `dbt/target/manifest.json`, keyed by its Dagster
    asset key (`silver_<name>` or `seed_<name>`, the same translator
    `dagster_defs.assets_dbt._Translator` uses), with its own description, its
    column names and how many of the manifest's test nodes it owns."""
    nodes = manifest["nodes"]
    owners: dict[str, str] = {
        uid: n["resource_type"]
        for uid, n in nodes.items()
        if n["resource_type"] in ("model", "seed")
    }
    tests: dict[str, int] = {}
    for uid, n in nodes.items():
        if n["resource_type"] != "test":
            continue
        owner = _test_owner(uid, n)
        tests[owner] = tests.get(owner, 0) + 1

    out: dict[str, DbtNode] = {}
    for uid, kind in owners.items():
        n = nodes[uid]
        is_gold = kind == "model" and "gold" in n.get("tags", [])
        prefix = "seed" if kind == "seed" else "gold" if is_gold else "silver"
        key = f"{prefix}_{n['name']}"
        out[key] = DbtNode(
            description=str(n.get("description") or ""),
            columns=sorted(n.get("columns", {})),
            tests=tests.get(uid, 0),
        )
    return out


def dbt_source_descriptions(manifest: dict[str, Any]) -> dict[str, str]:
    """The description of every dbt source table, keyed by the bronze asset key
    it documents (`bronze_<sport>_<table>`, the source name minus `bronze_`)."""
    out: dict[str, str] = {}
    for src in manifest.get("sources", {}).values():
        name = str(src["source_name"])
        if name.startswith("bronze_"):
            out[f"{name}_{src['name']}"] = str(src.get("description") or "").strip()
    return out


def undescribed(payload: dict[str, Any]) -> list[str]:
    """Keys of the nodes whose description is empty or blank."""
    return [n["key"] for n in payload.get("nodes", []) if not str(n.get("description", "")).strip()]


def _sport(key: str) -> str | None:
    for sport in ("basketball", "football"):
        if sport in key:
            return sport
    return None


def _bronze_schema(key: str, schemas_dir: Path) -> str:
    """`frozen` when `bronze/schemas/<sport>/<table>.schema.json` pins this
    table (28 of the 40), `code` when it is pyarrow in code instead (the rest,
    and `bronze_common_orientation`, which has no per-sport schema file)."""
    rest = key.removeprefix("bronze_")
    for sport in ("basketball", "football"):
        prefix = f"{sport}_"
        if rest.startswith(prefix):
            table = rest.removeprefix(prefix)
            if (schemas_dir / sport / f"{table}.schema.json").is_file():
                return "frozen"
            break
    return "code"


def schema_kind(key: str, group: str, schemas_dir: Path) -> str:
    if group == "bronze" and key.startswith("bronze_"):
        return _bronze_schema(key, schemas_dir)
    if group in ("silver", "gold"):
        return "dbt"
    return "none"


def lineage_from_defs(
    defs: Definitions,
    dbt_manifest_path: Path = DBT_MANIFEST,
    schemas_dir: Path = SCHEMAS_DIR,
) -> dict[str, Any]:
    """The whole payload: `groups`, every node of `defs.resolve_asset_graph()`
    (kind, group, description, the step that writes it, its sport if the name
    carries one, where its schema is pinned, and for the 12 dbt nodes their
    test count and columns) and every edge from `parent_keys`."""
    graph = defs.resolve_asset_graph()
    job = defs.resolve_job_def("build")
    layer = job.asset_layer
    manifest = (
        json.loads(dbt_manifest_path.read_text(encoding="utf-8"))
        if dbt_manifest_path.is_file()
        else {}
    )
    dbt = dbt_nodes(manifest) if manifest else {}
    sources = dbt_source_descriptions(manifest)

    keys = sorted(graph.get_all_asset_keys(), key=lambda k: k.to_user_string())
    nodes: list[dict[str, Any]] = []
    for key in keys:
        node = graph.get(key)
        key_str = key.to_user_string()
        if node.group_name not in GROUPS_IN_FLOW:
            raise ValueError(f"{key_str}: unknown group {node.group_name!r}")
        step = None if node.is_external else layer.get_op_output_handle(key).node_handle.name
        entry: dict[str, Any] = {
            "key": key_str,
            "group": node.group_name,
            "kind": "external" if node.is_external else "asset",
            "description": (
                dbt[key_str].description
                if key_str in dbt
                else (node.description or sources.get(key_str, ""))
            ),
            "step": step,
            "sport": _sport(key_str),
            "schema": schema_kind(key_str, node.group_name, schemas_dir),
        }
        if key_str in dbt:
            entry["dbt_tests"] = dbt[key_str].tests
            entry["dbt_columns"] = dbt[key_str].columns
        nodes.append(entry)

    edges = sorted(
        {
            (parent.to_user_string(), key.to_user_string())
            for key in keys
            for parent in graph.get(key).parent_keys
        }
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "groups": list(GROUPS_IN_FLOW),
        "nodes": nodes,
        "edges": [{"from": f, "to": t} for f, t in edges],
    }


def lineage_path(out_dir: Path) -> Path:
    return out_dir / LINEAGE_JSON


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def changed_keys(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Every node key present in only one side, or present in both with a
    different value: what `--check` prints when the versioned file differs."""
    old_nodes = {n["key"]: n for n in old.get("nodes", [])}
    new_nodes = {n["key"]: n for n in new.get("nodes", [])}
    same = old_nodes.keys() & new_nodes.keys()
    modified = {k for k in same if old_nodes[k] != new_nodes[k]}
    return sorted((old_nodes.keys() ^ new_nodes.keys()) | modified)


def run_publish_lineage(
    out_dir: Path, *, check: bool = False, dbt_manifest_path: Path = DBT_MANIFEST
) -> int:
    if not dbt_manifest_path.is_file():
        print(f"publish lineage: {dbt_manifest_path} missing; run `dbt parse` first")
        return 1

    from tracklab.dagster_defs import defs

    payload = lineage_from_defs(defs, dbt_manifest_path=dbt_manifest_path)
    text = render(payload)
    sha1 = hashlib.sha1(text.encode("utf-8")).hexdigest()
    path = lineage_path(out_dir)
    n_tests = sum(n.get("dbt_tests", 0) for n in payload["nodes"])
    print(
        f"publish lineage: {len(payload['nodes'])} nodes, {len(payload['edges'])} edges, "
        f"dbt_tests={n_tests}, sha1={sha1}"
    )

    blank = undescribed(payload)
    if blank:
        print(f"publish lineage: {len(blank)} node(s) without a description: {blank}")
        return 1

    if check:
        if not path.is_file():
            print(f"publish lineage --check: {path} missing")
            return 1
        current_text = path.read_text(encoding="utf-8")
        published_blank = undescribed(json.loads(current_text))
        if published_blank:
            print(
                f"publish lineage --check: {path} publishes {len(published_blank)} node(s) "
                f"without a description: {published_blank}"
            )
            return 1
        if current_text == text:
            print(f"publish lineage --check: {path} matches, sha1={sha1}")
            return 0
        changed = changed_keys(json.loads(current_text), payload)
        print(
            f"publish lineage --check: {path} differs, "
            f"{len(changed)} node key(s) changed: {changed}"
        )
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"publish lineage: {path} ({path.stat().st_size} bytes)")
    return 0
