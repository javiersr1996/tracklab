"""The dbt project as assets: silver models ``silver_<name>``, seeds ``seed_<name>``
and gold models ``gold_<name>`` (task 40, a step of its own: ``gold``).

A dbt source takes the key of the asset that writes it (``bronze_basketball_matches``,
``reports_orientation_basketball``, ``manifest_sources``), so the lineage runs from
the raw bytes to silver without a gap. dbt's tests become asset checks.

Silver is incremental (P16, task 127, ``silver/incremental.py``): the step rebuilds the
partitions of the matches whose inputs changed, and does not launch dbt when none did. It
says which, and why, in an observation the build record reads. Gold is skipped the same way
when its one fingerprint is unchanged (task 129).
"""

import json
import os
from collections.abc import Iterator, Mapping
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetObservation,
    MaterializeResult,
    MetadataValue,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from tracklab.cli import require_full
from tracklab.paths import DATA_ROOT_ENV, data_root
from tracklab.silver import dbt_plugin, incremental

dbt_project = DbtProject(project_dir=Path("dbt").resolve())
dbt_project.prepare_if_dev()
# What silver's sources read besides the data root (`models/sources/common.yml`).
REPORTS_DIR = Path("reports")
MANIFEST_DIR = Path("manifest")

# Every dbt step opens the one `tracklab.duckdb`, and DuckDB lets a single process write
# it: `definitions.py` caps the steps carrying this tag at one at a time.
DUCKDB_TAG = {"tracklab/duckdb": "dbt"}


def _is_gold(props: Mapping[str, Any]) -> bool:
    return props["resource_type"] == "model" and "gold" in props.get("tags", [])


class _Translator(DagsterDbtTranslator):
    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        kind, name = dbt_resource_props["resource_type"], dbt_resource_props["name"]
        if kind == "source":
            return AssetKey(f"{dbt_resource_props['source_name']}_{name}")
        if _is_gold(dbt_resource_props):
            return AssetKey(f"gold_{name}")
        return AssetKey(f"{'seed' if kind == 'seed' else 'silver'}_{name}")

    def get_group_name(self, dbt_resource_props: Mapping[str, Any]) -> str:
        return "gold" if _is_gold(dbt_resource_props) else "silver"


def _observation(
    plan: incremental.Plan, selected: list[AssetKey], preferred: AssetKey
) -> AssetObservation:
    """What the build record reads of a step's plan, on `preferred` or else the first asset."""
    return AssetObservation(
        asset_key=preferred if preferred in selected else selected[0],
        metadata={incremental.PLAN_METADATA_KEY: MetadataValue.json(plan.record())},
    )


def _skipped(
    context: AssetExecutionContext, plan: incremental.Plan, selected: list[AssetKey]
) -> Iterator[MaterializeResult[Any]]:
    """Every selected asset, materialized without launching dbt. A multi-asset yields its
    assets in dependency order (Dagster refuses any other)."""
    deps = context.assets_def.asset_deps
    order = TopologicalSorter({k: deps[k] & set(selected) for k in selected}).static_order()
    for key in order:
        yield MaterializeResult(
            asset_key=key, metadata={"tracklab/dbt": f"not launched: {plan.reason}"}
        )


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=_Translator(),
    exclude="tag:gold",
    op_tags=DUCKDB_TAG,
)
def silver(context: AssetExecutionContext, dbt: DbtCliResource) -> Iterator[Any]:
    # dagster-dbt runs dbt with the project directory as cwd, and every path the
    # project reads is relative to pipeline/: hand them over absolute.
    root = data_root().resolve()
    os.environ[DATA_ROOT_ENV] = str(root)
    os.environ["TRACKLAB_SILVER_MODELS"] = str(Path("dbt/models/silver").resolve())
    dbt_vars: dict[str, Any] = {
        "reports_dir": REPORTS_DIR.resolve().as_posix(),
        "manifest_path": MANIFEST_DIR.resolve().as_posix(),
    }
    manifest = json.loads(dbt_project.manifest_path.read_text(encoding="utf-8"))
    inputs = incremental.Inputs(
        root,
        REPORTS_DIR.resolve(),
        MANIFEST_DIR.resolve(),
        Path("dbt").resolve(),
        Path(dbt_plugin.__file__),
    )
    whole_step = context.selected_asset_keys == context.assets_def.keys
    fingerprints = incremental.fingerprints(incremental.silver_sources(manifest), inputs)
    state = incremental.read_state(root)
    forced = incremental.full_reason(
        full=bool(os.environ.get(incremental.FULL_ENV)),
        require_full=require_full(),
        whole_step=whole_step,
    )
    plan = incremental.make_plan(
        fingerprints, state, root, incremental.external_models(manifest), forced
    )
    context.log.info(f"silver {plan.mode}: {plan.reason}")
    selected = sorted(context.selected_asset_keys, key=lambda key: key.to_user_string())
    observation = _observation(plan, selected, AssetKey("silver_frames"))
    if plan.mode == "skip":
        yield observation
        yield from _skipped(context, plan, selected)
        return
    names = {key.to_user_string() for key in selected}
    partitioned = [m for m in incremental.PARTITIONED if f"silver_{m}" in names]
    incremental.prepare(plan, state, root, partitioned)
    dbt_vars |= plan.dbt_vars()
    yield from dbt.cli(["build", "--vars", json.dumps(dbt_vars)], context=context).stream()
    incremental.finish(fingerprints, root, context.run_id, whole_step=whole_step)
    yield observation


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=_Translator(),
    select="tag:gold",
    op_tags=DUCKDB_TAG,
)
def gold(context: AssetExecutionContext, dbt: DbtCliResource) -> Iterator[Any]:
    """The six season aggregates and the dimensional model, from the bronze aggregates. Skipped
    when nothing it depends on changed (`silver/incremental.py`, task 129)."""
    os.environ[DATA_ROOT_ENV] = str(data_root().resolve())
    os.environ["TRACKLAB_GOLD_MODELS"] = str(Path("dbt/models/gold").resolve())
    root = data_root().resolve()
    manifest = json.loads(dbt_project.manifest_path.read_text(encoding="utf-8"))
    inputs = incremental.Inputs(
        root,
        REPORTS_DIR.resolve(),
        MANIFEST_DIR.resolve(),
        Path("dbt").resolve(),
        Path(dbt_plugin.__file__),
    )
    whole_step = context.selected_asset_keys == context.assets_def.keys
    fingerprint = incremental.gold_fingerprint(incremental.gold_sources(manifest), inputs)
    forced = incremental.full_reason(
        full=bool(os.environ.get(incremental.FULL_ENV)),
        require_full=require_full(),
        whole_step=whole_step,
        step="gold",
    )
    plan = incremental.make_gold_plan(
        fingerprint,
        incremental.read_state(root, incremental.GOLD),
        root,
        incremental.external_models(manifest, gold=True),
        forced,
    )
    context.log.info(f"gold {plan.mode}: {plan.reason}")
    selected = sorted(context.selected_asset_keys, key=lambda key: key.to_user_string())
    observation = _observation(plan, selected, selected[0])
    if plan.mode == "skip":
        yield observation
        yield from _skipped(context, plan, selected)
        return
    incremental.forget_gold(root)
    yield from dbt.cli(["build"], context=context).stream()
    incremental.finish_gold(fingerprint, root, context.run_id, whole_step=whole_step)
    yield observation
