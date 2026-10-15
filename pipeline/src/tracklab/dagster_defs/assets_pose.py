"""``pose_*`` and ``publish_pose``: the P6 artefacts in the graph, group ``pose`` (task 64).

Like the ``runs`` group, these never write: each runs the ``--check`` of its command, which
recomputes the versioned artefact from the bronze at ``data_root()`` and compares it with the file
in the repository (``FULL n/n`` on the whole bronze, ``PARTIAL`` on a slice, which says what it
verified). A write here would be wrong twice: the metric and the publication read the confirmation
match only past the guard, which refuses a dirty tree, and a check that follows its own write
compares a file with itself. The asset fails when the check exits non-zero.

Not part of ``group:silver`` or ``group:gold``, so CI's run on the fixtures never selects them.
``full-build`` selects everything but this group and the runs one, and runs the four checks as
steps of their own, after the build: the metric takes about half an hour, and a step of its own
names the one that failed.
"""

from pathlib import Path

from dagster import AssetExecutionContext, Failure, asset

from tracklab.dagster_defs.assets_runs import REPORTS_DIR, WEB_DATA_DIR, check_asset
from tracklab.paths import data_root
from tracklab.pose.coverage import run_pose_coverage
from tracklab.pose.metric import run_pose_metric
from tracklab.pose.protocol import run_pose_protocol
from tracklab.publish.pose import run_publish_pose

# Relative to pipeline/, like the paths of the other publish assets.
MANIFEST = Path("manifest/sources.json")
SCHEMA = Path("../web/lib/pose/schema.json")

# The bronze the checks read: the pose of both matches and the lineup that orders their players.
_BRONZE = (
    "bronze_football_bodypose_frames",
    "bronze_football_bodypose_players",
    "bronze_football_match_players",
)

pose_coverage = check_asset(
    "pose_coverage",
    "pose coverage",
    lambda data, reports: run_pose_coverage(data, reports, check=True),
    list(_BRONZE),
    "reports/pose_coverage.json: frames, player-frames and joints with a pose per match, checked.",
    group="pose",
)
pose_protocol = check_asset(
    "pose_protocol",
    "pose protocol",
    lambda data, reports: run_pose_protocol(data, reports, check=True),
    [*_BRONZE, "pose_coverage"],
    "reports/pose_protocol.json: the frozen protocol against the code and the denominators.",
    group="pose",
)
pose_metric = check_asset(
    "pose_metric",
    "pose metric",
    lambda data, reports: run_pose_metric(data, reports, check=True),
    [*_BRONZE, "pose_protocol"],
    "reports/pose_metric.json: the metric in both matches, recomputed and compared.",
    group="pose",
)


@asset(
    name="publish_pose",
    group_name="pose",
    deps=[
        "pose_metric",
        "pose_coverage",
        "pose_protocol",
        "raw_football",
        "bronze_football_match",
        "bronze_football_tracking_objects",
        *_BRONZE,
    ],
    description="web/public/data/pose.json and pose/*.json, regenerated and compared.",
)
def publish_pose(context: AssetExecutionContext) -> None:
    if run_publish_pose(data_root(), REPORTS_DIR, WEB_DATA_DIR, MANIFEST, SCHEMA, check=True) != 0:
        raise Failure("tracklab publish pose --check failed")


pose_assets = [pose_coverage, pose_protocol, pose_metric, publish_pose]
