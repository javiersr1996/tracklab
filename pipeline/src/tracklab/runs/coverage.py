"""`tracklab runs coverage`: what the tracking holds around each off-ball run, as counts (task 48).

One row per match for all 20, held-out included: counting runs, windows and detected
positions is not an outcome (see `data.counting_match_ids`). Every match is counted by
`windows.count_tracking`, which reads its frames and runs, counts and drops them in its own
scope: no tracking comes back to this module. The file holds integers and detection fractions and
nothing else; `count_match` has no way to return a position, a displacement or a line height,
and this module only formats what it returns.

`--check` regenerates the rows of the matches present in the warehouse at hand and compares
them with the versioned file; on the CI fixtures (a slice of one match) it can recount none
of the 20 and says so with a `PARTIAL 0/20` status, the other rows being covered only where
the whole warehouse exists (lesson of task 47). The ids and the halves come from the protocol
committed in HEAD (`data`), never from a file at hand.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from tracklab.runs.data import counting_match_ids, match_halves
from tracklab.runs.windows import (
    COUNT_FIELDS,
    SUBTYPES,
    MatchCounts,
    count_tracking,
    load_runs,
)

COVERAGE_NAME = "runs_coverage.csv"
HEADER = (
    "match_id",
    "half",
    "runs",
    *(f"runs_{s}" for s in SUBTYPES),
    *(f for f in COUNT_FIELDS if f not in ("match_id", "runs")),
)


def _has_frames(data_dir: Path, match_id: int) -> bool:
    folder = data_dir / "silver" / "frames" / "sport=football" / f"native_match_id={match_id}"
    return folder.is_dir()


def _row(counts: MatchCounts, half: str) -> list[str]:
    values: dict[str, str] = {"match_id": str(counts.match_id), "half": half}
    for name in COUNT_FIELDS:
        v = getattr(counts, name)
        values[name] = f"{v:.4f}" if isinstance(v, float) else str(v)
    for subtype, n in zip(SUBTYPES, counts.by_subtype, strict=True):
        values[f"runs_{subtype}"] = str(n)
    return [values[h] for h in HEADER]


def coverage_rows(data_dir: Path, match_ids: list[int]) -> list[list[str]]:
    halves = match_halves()
    rows = []
    for match_id in match_ids:
        half = halves[match_id]
        counts = count_tracking(data_dir, match_id)
        rows.append(_row(counts, half))
    return rows


def render(rows: list[list[str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return out.getvalue()


def run_runs_coverage(data_dir: Path, reports_dir: Path, *, check: bool = False) -> int:
    wanted = counting_match_ids()
    at_hand = [m for m in wanted if _has_frames(data_dir, m)]
    path = reports_dir / COVERAGE_NAME
    if not check:
        if at_hand != wanted:
            print(
                f"runs coverage: silver frames for {len(at_hand)} of the {len(wanted)} matches "
                f"under {data_dir}; the file is written from all of them or not at all"
            )
            return 1
        rows = coverage_rows(data_dir, wanted)
        reports_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(render(rows), encoding="utf-8", newline="\n")
        print(_summary(rows, len(rows)))
        print(f"runs coverage: {path} ({path.stat().st_size} bytes)")
        return 0
    if not path.is_file():
        print(f"runs coverage --check: {path} missing")
        return 1
    if not at_hand:
        print(f"runs coverage --check: no football frames under {data_dir}")
        return 1
    current = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))
    if tuple(current[0]) != HEADER:
        print("runs coverage --check: the header differs")
        return 1
    committed = {r[0]: r for r in current[1:]}
    if sorted(int(m) for m in committed) != wanted:
        print("runs coverage --check: the matches of the file are not those of the protocol")
        return 1
    # A match whose bronze holds fewer runs than the file is a slice (the CI fixtures cut one
    # possession per sport): its counts cannot be rehearsed, so only the rest is verified.
    whole: list[int] = []
    slices: list[int] = []
    for match_id in at_hand:
        n = len(load_runs(data_dir, match_id))
        (whole if n == int(committed[str(match_id)][HEADER.index("runs")]) else slices).append(
            match_id
        )
    unexplained = [
        m
        for m in slices
        if len(load_runs(data_dir, m)) > int(committed[str(m)][HEADER.index("runs")])
    ]
    if unexplained:
        print(f"runs coverage --check: more runs than the file holds for {unexplained}")
        return 1
    fresh = coverage_rows(data_dir, whole) if whole else []
    stale = [r[0] for r in fresh if committed[r[0]] != r]
    if stale:
        print(f"runs coverage --check: rows differ for {stale}")
        return 1
    status = "FULL" if len(whole) == len(wanted) else "PARTIAL"
    print(
        f"runs coverage --check: warehouse={status} {len(whole)}/{len(wanted)} rows recounted "
        f"and equal, {len(slices)} present only as slices (header and match list verified), "
        f"{path} matches"
    )
    return 0


def _summary(rows: list[list[str]], n: int) -> str:
    column = {h: i for i, h in enumerate(HEADER)}
    total = {
        h: sum(int(r[column[h]]) for r in rows)
        for h in ("runs", "complete_windows", "runner_detected", "clean", "placebo_found")
    }
    return f"runs coverage: matches={n} " + " ".join(f"{k}={v}" for k, v in total.items())
