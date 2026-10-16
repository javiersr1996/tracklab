"""``runs_*`` and ``publish_runs``: the P5 artefacts in the graph, group ``runs`` (decision 6).

P5 died at M5a (task 50) with its protocol in stage ``design``, so these assets never write: each
runs the ``--check`` of its command, which recomputes the versioned artefact from the warehouse
at ``data_root()`` and compares it with the file in the repository. A write here would be wrong
twice: the probe and the effect record ``head`` and ``code_tree_sha`` and refuse a dirty tree,
and a check that follows its own write compares a file with itself. The asset fails when the
check exits non-zero.

Not part of ``group:silver`` or ``group:gold``, so CI's run on the fixtures never selects them.
``full-build`` selects everything but this group and runs the five checks as steps of their
own, after the build: the probe takes minutes, and a step of its own names the one that failed.
"""

# No `from __future__ import annotations`: Dagster reads the `context` hint at runtime.
from collections.abc import Callable
from pathlib import Path

from dagster import AssetExecutionContext, AssetsDefinition, Failure, asset

from tracklab.paths import data_root
from tracklab.publish.runs import run_publish_runs
from tracklab.runs.candidates import run_runs_effect
from tracklab.runs.coverage import run_runs_coverage
from tracklab.runs.probe import run_runs_probe
from tracklab.runs.protocol import run_runs_protocol

# Relative to pipeline/, like the paths of the publish assets.
WEB_DATA_DIR = Path("../web/public/data")
REPORTS_DIR = Path("reports")

# The silver and bronze tables the checks read (`runs/windows.py`, `placebo.py`, `probe.py`).
_TRACKING = (
    "silver_frames",
    "silver_dim_period",
    "silver_dim_team_period",
    "bronze_football_dynamic_events",
    "bronze_football_match_players",
    "bronze_football_match",
)

Check = Callable[[Path, Path], int]


def check_asset(
    name: str, command: str, run: Check, deps: list[str], description: str, group: str = "runs"
) -> AssetsDefinition:
    @asset(name=name, group_name=group, deps=deps, description=description)
    def _run(context: AssetExecutionContext) -> None:
        if run(data_root(), REPORTS_DIR) != 0:
            raise Failure(f"tracklab {command} --check failed")

    return _run


runs_protocol = check_asset(
    "runs_protocol",
    "runs protocol",
    lambda data, reports: run_runs_protocol(data, reports, check=True),
    ["silver_dim_match", "quality_partitions", "bronze_football_dynamic_events"],
    "reports/runs_protocol.json: the split, the windows and the death criteria, checked.",
)
runs_coverage = check_asset(
    "runs_coverage",
    "runs coverage",
    lambda data, reports: run_runs_coverage(data, reports, check=True),
    [*_TRACKING, "runs_protocol"],
    "reports/runs_coverage.csv: runs, windows and placebos per match, checked.",
)
runs_probe = check_asset(
    "runs_probe",
    "runs probe",
    lambda data, reports: run_runs_probe(data, reports, check=True),
    [*_TRACKING, "runs_coverage"],
    "reports/runs_calibration.json, section probe (M1, M2), recomputed and compared.",
)
runs_effect = check_asset(
    "runs_effect",
    "runs effect",
    lambda data, reports: run_runs_effect(data, reports, check=True),
    [*_TRACKING, "runs_probe"],
    "reports/runs_calibration.json, section effect (M3 to M5a), recomputed and compared.",
)


@asset(
    name="publish_runs",
    group_name="runs",
    deps=["runs_effect", "runs_coverage", "runs_protocol"],
    description="web/public/data/runs.json and runs/*.json, regenerated and compared.",
)
def publish_runs(context: AssetExecutionContext) -> None:
    if run_publish_runs(data_root(), REPORTS_DIR, WEB_DATA_DIR, check=True) != 0:
        raise Failure("tracklab publish runs --check failed")


runs_assets = [runs_protocol, runs_coverage, runs_probe, runs_effect, publish_runs]
