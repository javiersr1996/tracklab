"""`tracklab publish lineage` (task 33): the exported graph against the real
`defs` and its dbt manifest, plus the fabricated-manifest cases that decide
which model owns a test.

Needs `dbt/target/manifest.json` (`dbt parse` first, as CI does before pytest;
see `tests/unit/test_dagster_defs.py`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tracklab.dagster_defs import defs
from tracklab.publish.lineage import (
    GROUPS_IN_FLOW,
    changed_keys,
    dbt_nodes,
    lineage_from_defs,
    render,
    schema_kind,
)


def _model(name: str, description: str = "", columns: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "resource_type": "model",
        "name": name,
        "description": description,
        "columns": {c: {} for c in columns},
    }


def _seed(name: str, description: str = "", columns: tuple[str, ...] = ()) -> dict[str, Any]:
    return {**_model(name, description, columns), "resource_type": "seed"}


def _test(attached: str | None, deps: list[str]) -> dict[str, Any]:
    return {"resource_type": "test", "attached_node": attached, "depends_on": {"nodes": deps}}


# --- lineage_from_defs against the real graph --------------------------------------


def test_lineage_from_defs_returns_exactly_the_graphs_keys() -> None:
    payload = lineage_from_defs(defs)
    graph = defs.resolve_asset_graph()
    expected = {k.to_user_string() for k in graph.get_all_asset_keys()}
    assert {n["key"] for n in payload["nodes"]} == expected
    assert {n["group"] for n in payload["nodes"]} <= set(GROUPS_IN_FLOW)


def test_the_pose_group_closes_the_exported_flow_with_its_four_assets() -> None:
    payload = lineage_from_defs(defs)
    assert payload["groups"][-1] == "pose"
    assert {n["key"] for n in payload["nodes"] if n["group"] == "pose"} == {
        "pose_coverage",
        "pose_protocol",
        "pose_metric",
        "publish_pose",
    }


def test_the_runs_group_is_in_the_exported_flow_with_its_five_assets() -> None:
    payload = lineage_from_defs(defs)
    assert "runs" in payload["groups"]
    assert {n["key"] for n in payload["nodes"] if n["group"] == "runs"} == {
        "runs_protocol",
        "runs_coverage",
        "runs_probe",
        "runs_effect",
        "publish_runs",
    }


def test_every_edge_has_both_ends_among_nodes() -> None:
    payload = lineage_from_defs(defs)
    keys = {n["key"] for n in payload["nodes"]}
    assert payload["edges"], "no edges at all: the graph or the export is broken"
    for edge in payload["edges"]:
        assert edge["from"] in keys
        assert edge["to"] in keys


def test_dropping_manifest_sources_breaks_the_edges_invariant() -> None:
    """The mutation tasks/todo.md asks for: remove `manifest_sources` from the
    exported nodes and the edges test above would fail, because bronze's raw_*
    edges still point at it. Proven here without touching the real export."""
    payload = lineage_from_defs(defs)
    keys = {n["key"] for n in payload["nodes"] if n["key"] != "manifest_sources"}
    broken = [e for e in payload["edges"] if e["from"] not in keys or e["to"] not in keys]
    assert broken, "removing manifest_sources should orphan at least one edge"


def test_two_builds_of_the_real_graph_produce_the_same_bytes() -> None:
    a = render(lineage_from_defs(defs))
    b = render(lineage_from_defs(defs))
    assert a == b
    assert "\r\n" not in a


def test_lineage_names_no_local_machine(assert_no_local_traces: Callable[[object], None]) -> None:
    assert_no_local_traces(lineage_from_defs(defs))


def test_dbt_tests_sum_matches_the_manifests_own_test_count() -> None:
    manifest = json.loads(Path("dbt/target/manifest.json").read_text(encoding="utf-8"))
    n_test_nodes = sum(1 for n in manifest["nodes"].values() if n["resource_type"] == "test")
    payload = lineage_from_defs(defs)
    assert sum(n.get("dbt_tests", 0) for n in payload["nodes"]) == n_test_nodes


# --- dbt_nodes: which model or seed owns a test -------------------------------------


def test_generic_test_is_attributed_via_attached_node() -> None:
    manifest = {
        "nodes": {
            "model.x.dim_a": _model("dim_a", "A", ("id",)),
            "model.x.dim_b": _model("dim_b", "B", ("id",)),
            "test.x.rel": _test("model.x.dim_a", ["model.x.dim_b", "model.x.dim_a"]),
        }
    }
    nodes = dbt_nodes(manifest)
    assert nodes["silver_dim_a"].tests == 1
    assert nodes["silver_dim_b"].tests == 0


def test_singular_test_with_two_deps_is_attributed_to_the_first_one() -> None:
    """`assert_frames_entities_in_dim_entity` and `assert_one_ball_per_match` in
    the real project both depend on two models with no `attached_node`; in
    both, `depends_on.nodes[0]` is the `FROM`-clause model. Reproduced here
    with a fabricated pair rather than a re-read of the real manifest."""
    manifest = {
        "nodes": {
            "model.x.frames": _model("frames"),
            "model.x.dim_entity": _model("dim_entity"),
            "test.x.assert_x": _test(None, ["model.x.frames", "model.x.dim_entity"]),
        }
    }
    nodes = dbt_nodes(manifest)
    assert nodes["silver_frames"].tests == 1
    assert nodes["silver_dim_entity"].tests == 0


def test_a_seed_can_own_a_test_too() -> None:
    manifest = {
        "nodes": {
            "seed.x.surface_spec": _seed("surface_spec", "specs", ("length_m",)),
            "test.x.not_null": _test("seed.x.surface_spec", ["seed.x.surface_spec"]),
        }
    }
    nodes = dbt_nodes(manifest)
    assert nodes["seed_surface_spec"].tests == 1
    assert nodes["seed_surface_spec"].columns == ["length_m"]


def test_a_singular_test_naming_no_model_or_seed_is_an_error() -> None:
    manifest = {
        "nodes": {
            "model.x.frames": _model("frames"),
            "test.x.broken": _test(None, []),
        }
    }
    with pytest.raises(ValueError, match="test.x.broken"):
        dbt_nodes(manifest)


# --- schema_kind: frozen, code, dbt or none ------------------------------------------


def test_schema_kind_is_frozen_only_when_the_file_exists(tmp_path: Path) -> None:
    schemas = tmp_path / "schemas"
    (schemas / "basketball").mkdir(parents=True)
    (schemas / "basketball" / "events_shots.schema.json").write_text("{}", encoding="utf-8")

    assert schema_kind("bronze_basketball_events_shots", "bronze", schemas) == "frozen"
    assert schema_kind("bronze_basketball_tracking_objects", "bronze", schemas) == "code"
    assert schema_kind("bronze_common_orientation", "bronze", schemas) == "code"
    assert schema_kind("silver_frames", "silver", schemas) == "dbt"
    assert schema_kind("seed_event_type_map", "silver", schemas) == "dbt"
    assert schema_kind("quality_detection", "quality", schemas) == "none"
    assert schema_kind("manifest_sources", "ingest", schemas) == "none"


# --- changed_keys: what --check reports ----------------------------------------------


def test_changed_keys_reports_added_removed_and_modified() -> None:
    old = {"nodes": [{"key": "a", "v": 1}, {"key": "b", "v": 1}, {"key": "c", "v": 1}]}
    new = {"nodes": [{"key": "a", "v": 1}, {"key": "b", "v": 2}, {"key": "d", "v": 1}]}
    assert changed_keys(old, new) == ["b", "c", "d"]


def test_changed_keys_is_empty_for_identical_payloads() -> None:
    payload = {"nodes": [{"key": "a", "v": 1}]}
    assert changed_keys(payload, payload) == []
