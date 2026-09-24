"""`tracklab quality`: run checks, write one CSV each, print where it went."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from tracklab.quality import clock, detection, entry_angle, gravity, noise, partitions
from tracklab.quality.common import Result, write_results

# (data_dir, reports_dir) -> its rows. `reports_dir` is unused by most checks (they
# read only silver/bronze); `partitions` is the one that reads other already-written
# reports, and the shared signature keeps `CHECKS` a single, uniform dict.
Check = Callable[[Path, Path], list[Result]]

CHECKS: dict[str, Check] = {
    detection.CHECK: detection.detection,
    gravity.CHECK: gravity.gravity,
    entry_angle.CHECK: entry_angle.entry_angle,
    noise.CHECK: noise.noise,
    clock.CHECK: clock.clock,
    partitions.CHECK: partitions.partitions,
}


def run_quality(checks: Sequence[str], data_dir: Path, reports_dir: Path) -> int:
    unknown = [c for c in checks if c not in CHECKS]
    if unknown:
        print(f"quality: unknown check(s) {unknown}, known: {sorted(CHECKS)}")
        return 1
    for check in checks:
        results = CHECKS[check](data_dir, reports_dir)
        path = write_results(reports_dir, check, results)
        matches = len({(r.sport, r.match_id) for r in results})
        print(f"quality {check}: {len(results)} rows over {matches} matches, {path}")
    return 0
