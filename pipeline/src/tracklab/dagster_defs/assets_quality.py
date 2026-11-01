"""``quality_<check>``: one asset per data quality check (P3), group ``quality``.

Not part of ``group:silver``, so CI's run on the fixtures never writes a quality
report: the reports are versioned and describe the full bundles.
"""

# No `from __future__ import annotations`: Dagster reads the `context` hint at runtime.
from pathlib import Path

from dagster import AssetExecutionContext, AssetsDefinition, Failure, asset

from tracklab.paths import data_root
from tracklab.quality.run import CHECKS, run_quality

# The silver (and bronze) tables each check reads.
READS: dict[str, list[str]] = {
    "detection": ["silver_frames"],
    "gravity": ["silver_frames", "bronze_basketball_events_shots"],
    "entry_angle": ["silver_frames", "bronze_basketball_events_shots"],
    "noise": ["silver_frames", "bronze_basketball_tracking_objects"],
    "clock": [
        "bronze_basketball_tracking_frames",
        "bronze_basketball_tracking_objects",
        "bronze_football_tracking_frames",
    ],
    # `football_format.csv` (task 4) is not itself a Dagster asset (`freeze-schema`
    # is a standalone CLI command, never materialized as one): this check reads it
    # as a static, already-versioned artefact, so it has no dep to declare here.
    "partitions": ["bronze_basketball_tracking_frames", "reports_orientation_football"],
}

# What each check measures, one line each (published as the node's description in lineage.json).
DESCRIPTIONS: dict[str, str] = {
    "detection": "How often the provider says it saw each kind of object, per match.",
    "gravity": "Apparent gravity of the ball per match: the g its free flights fall with.",
    "entry_angle": "Entry angle of a made shot: what the bundle reports against the geometry.",
    "noise": "Frame-to-frame jitter of the ball against detected players, both sports.",
    "clock": "Whether the clock is exact: the step between two native frames, per match.",
    "partitions": "The partitions no field in either bundle declares, one row per match.",
}


def _quality_asset(check: str) -> AssetsDefinition:
    @asset(
        name=f"quality_{check}",
        group_name="quality",
        deps=READS[check],
        description=DESCRIPTIONS[check],
    )
    def _run(context: AssetExecutionContext) -> None:
        if run_quality([check], data_dir=data_root(), reports_dir=Path("reports")) != 0:
            raise Failure(f"tracklab quality {check} failed")

    return _run


quality_assets = [_quality_asset(check) for check in sorted(CHECKS)]
