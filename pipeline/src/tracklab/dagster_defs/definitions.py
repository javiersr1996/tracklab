"""Every asset and the one resource they need, in a single ``Definitions``."""

from __future__ import annotations

from dagster import AssetSelection, Definitions, define_asset_job
from dagster_dbt import DbtCliResource

from tracklab.dagster_defs.assets_bronze import bronze_assets, orientation
from tracklab.dagster_defs.assets_dbt import dbt_project, silver
from tracklab.dagster_defs.assets_ingest import manifest_sources, raw_assets

# Every asset in one run, and the one command that works on Windows too: click expands
# a bare `--select "*"` against the working directory there.
build = define_asset_job("build", selection=AssetSelection.all())

defs = Definitions(
    assets=[manifest_sources, *raw_assets, *bronze_assets, orientation, silver],
    jobs=[build],
    resources={"dbt": DbtCliResource(project_dir=dbt_project)},
)
