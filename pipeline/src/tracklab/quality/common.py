"""What every quality check returns and how it lands on disk."""

from __future__ import annotations

import csv
from dataclasses import astuple, dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Result:
    """One measured number: `value` in `unit`, over `n` observations."""

    check: str
    sport: str
    match_id: str
    metric: str
    value: float
    unit: str
    n: int


def report_path(reports_dir: Path, check: str) -> Path:
    return reports_dir / f"quality_{check}.csv"


def write_results(reports_dir: Path, check: str, results: list[Result]) -> Path:
    """Sorted, so a rebuild with the same data writes the same bytes."""
    path = report_path(reports_dir, check)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(astuple(r) for r in results)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([f.name for f in fields(Result)])
        writer.writerows(rows)
    return path
