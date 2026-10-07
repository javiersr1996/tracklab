"""Every asset and the one resource they need, in a single ``Definitions``."""

from __future__ import annotations

from dagster import AssetSelection, Definitions, define_asset_job, multiprocess_executor
from dagster_dbt import DbtCliResource

from tracklab.dagster_defs.assets_bronze import bronze_assets, orientation
from tracklab.dagster_defs.assets_dbt import DUCKDB_TAG, dbt_project, gold, silver
from tracklab.dagster_defs.assets_ingest import manifest_sources, raw_assets
from tracklab.dagster_defs.assets_publish import publish_possessions, publish_quality, publish_stats
from tracklab.dagster_defs.assets_quality import quality_assets

# Every asset in one run, and the one command that works on Windows too: click expands
# a bare `--select "*"` against the working directory there.
_one_at_a_time = [{"key": k, "value": v, "limit": 1} for k, v in DUCKDB_TAG.items()]
build = define_asset_job("build", selection=AssetSelection.all())

defs = Definitions(
    assets=[
        manifest_sources,
        *raw_assets,
        *bronze_assets,
        orientation,
        silver,
        gold,
        publish_possessions,
        publish_stats,
        *quality_assets,
        publish_quality,
    ],
    jobs=[build],
    # On the `Definitions`, not on `build`: the implicit job behind `dagster asset
    # materialize` and `dagster dev` inherits it, and DuckDB takes one writer at a time.
    executor=multiprocess_executor.configured({"tag_concurrency_limits": _one_at_a_time}),
    resources={"dbt": DbtCliResource(project_dir=dbt_project)},
)
