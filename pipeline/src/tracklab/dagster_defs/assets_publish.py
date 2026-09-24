"""``publish_possessions`` and ``publish_stats``: task 17's JSON for the web,
built from silver and, for the basketball quality filter, one bronze table.

Group ``publish``, deliberately not ``silver``: CI materializes
``group:silver`` on the fixtures and must never write into
``web/public/data``, which is versioned, so keeping this a separate group is
what makes that true without an extra exclusion flag anywhere.
"""

# No `from __future__ import annotations`: Dagster reads the `context` hint at runtime.
from pathlib import Path

from dagster import AssetExecutionContext, Failure, asset

from tracklab.paths import data_root
from tracklab.publish.possessions import run_publish_possessions
from tracklab.publish.stats import run_publish_stats

# Relative to pipeline/, like every other path task 15 documented.
WEB_DATA_DIR = Path("../web/public/data")

_SILVER_DEPS = (
    "silver_frames",
    "silver_events",
    "silver_dim_match",
    "silver_dim_team",
    "silver_dim_sport",
    "silver_dim_entity",
    "silver_dim_team_period",
)


@asset(
    name="publish_possessions",
    group_name="publish",
    deps=[*_SILVER_DEPS, "bronze_basketball_events_chances"],
    description="6 curated possessions per sport, written to web/public/data/possessions/.",
)
def publish_possessions(context: AssetExecutionContext) -> None:
    code = run_publish_possessions(data_root(), WEB_DATA_DIR)
    if code != 0:
        raise Failure(f"tracklab publish possessions exited with {code}")


@asset(
    name="publish_stats",
    group_name="publish",
    deps=[*_SILVER_DEPS, "publish_possessions", "manifest_sources"],
    description="web/public/data/stats.json: rows per table and sport, raw and published bytes.",
)
def publish_stats(context: AssetExecutionContext) -> None:
    code = run_publish_stats(data_root(), WEB_DATA_DIR)
    if code != 0:
        raise Failure(f"tracklab publish stats exited with {code}")
