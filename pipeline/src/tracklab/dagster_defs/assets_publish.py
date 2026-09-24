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
from tracklab.publish.quality import run_publish_quality
from tracklab.publish.stats import run_publish_stats
from tracklab.quality.run import CHECKS

# Relative to pipeline/, like every other path task 15 documented.
WEB_DATA_DIR = Path("../web/public/data")
REPORTS_DIR = Path("reports")
DOCS_DIR = Path("../docs")

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


@asset(
    name="publish_quality",
    group_name="publish",
    # The six reports, plus the two tables the hook shot re-reads directly
    # (`quality_gravity` reads them too, but that is its own asset's dependency,
    # not a transitive grant for this one).
    deps=[
        *(f"quality_{check}" for check in sorted(CHECKS)),
        "silver_frames",
        "bronze_basketball_events_shots",
    ],
    description="web/public/data/quality.json and docs/bulletin.md, from reports/quality_*.csv.",
)
def publish_quality(context: AssetExecutionContext) -> None:
    code = run_publish_quality(data_root(), REPORTS_DIR, WEB_DATA_DIR, DOCS_DIR)
    if code != 0:
        raise Failure(f"tracklab publish quality exited with {code}")
