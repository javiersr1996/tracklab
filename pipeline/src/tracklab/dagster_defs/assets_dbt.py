"""The dbt project as assets: silver models ``silver_<name>``, seeds ``seed_<name>``
and gold models ``gold_<name>`` (task 40, a step of its own: ``gold``).

A dbt source takes the key of the asset that writes it (``bronze_basketball_matches``,
``reports_orientation_basketball``, ``manifest_sources``), so the lineage runs from
the raw bytes to silver without a gap. dbt's tests become asset checks.
"""

import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from dagster import AssetExecutionContext, AssetKey
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from tracklab.paths import DATA_ROOT_ENV, data_root

dbt_project = DbtProject(project_dir=Path("dbt").resolve())
dbt_project.prepare_if_dev()

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
    os.environ[DATA_ROOT_ENV] = str(data_root().resolve())
    os.environ["TRACKLAB_SILVER_MODELS"] = str(Path("dbt/models/silver").resolve())
    dbt_vars = {
        "reports_dir": Path("reports").resolve().as_posix(),
        "manifest_path": Path("manifest").resolve().as_posix(),
    }
    yield from dbt.cli(["build", "--vars", json.dumps(dbt_vars)], context=context).stream()


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=_Translator(),
    select="tag:gold",
    op_tags=DUCKDB_TAG,
)
def gold(context: AssetExecutionContext, dbt: DbtCliResource) -> Iterator[Any]:
    """The six season aggregates and the dimensional model, from the bronze aggregates."""
    os.environ[DATA_ROOT_ENV] = str(data_root().resolve())
    os.environ["TRACKLAB_GOLD_MODELS"] = str(Path("dbt/models/gold").resolve())
    yield from dbt.cli(["build"], context=context).stream()
