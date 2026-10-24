"""Probe for lesson 9, "At what angle does the ball reach the rim?" (task 84). Read-only.

The table is P3's, already published: `checks.entry_angle` of `web/public/data/quality.json`,
five metrics per basketball match (reported and required median angle, their median gap, the
share of shot pairs the two angles order differently, and the shots kept). The probe prints it.

The example is one flight of 114086. For each made, unblocked shot of bronze `events_shots` with
a start, an end and a distance (P3's `_made_shots` rule), the ball rows of bronze
`tracking_objects` (ft, to m) go through P3's own `_angles` on the run `_match` would cut, so a
shot counts only if P3 accepted it; then the ball must be at every frame from `startFrame` to the
first frame after its highest one where z is at or under the rim, 3.048 m. Prints how many qualify
and the frames from `startFrame` to the rim of each.

Decided before measuring: the lesson lives if `quality.json` holds the five metrics for every
basketball match and at least one shot of 114086 qualifies as the example.

    TRACKLAB_DATA_ROOT=... uv run python scripts/probe_learn_entry.py
"""

from __future__ import annotations

import bisect
import json
from pathlib import Path

import duckdb

from tracklab.paths import data_root
from tracklab.quality.entry_angle import (
    MIN_CONTIG,
    RIM_HEIGHT,
    SEARCH_OFFSET,
    SEG_LEN,
    _angles,
    _contig_len,
)
from tracklab.quality.gravity import FT, Sample

MATCH = 114086
METRICS = (
    "angle_reported_median_deg",
    "angle_required_median_deg",
    "gap_median_deg",
    "pairs_reordered_pct",
    "shots",
)
QUALITY = Path(__file__).resolve().parents[2] / "web" / "public" / "data" / "quality.json"


def main() -> int:
    rows = json.loads(QUALITY.read_text(encoding="utf-8"))["checks"]["entry_angle"]
    table: dict[str, dict[str, float]] = {}
    for r in rows:
        table.setdefault(r["match_id"], {})[r["metric"]] = r["value"]
    print("probe entry: quality.json checks.entry_angle")
    print("match       reported  required  gap      reordered  shots")
    for match_id, m in sorted(table.items()):
        print(
            f"{match_id}  {m.get(METRICS[0])}  {m.get(METRICS[1])}  {m.get(METRICS[2])}"
            f"  {m.get(METRICS[3])}  {m.get(METRICS[4])}"
        )
    complete = len(table) == 10 and all(set(METRICS) <= set(m) for m in table.values())

    bronze = data_root() / "bronze" / "basketball"
    con = duckdb.connect()
    starts = [
        int(s)
        for (s,) in con.execute(
            "SELECT startFrame FROM read_parquet(?) WHERE outcome AND NOT blocked AND startFrame "
            "IS NOT NULL AND endFrame IS NOT NULL AND distance IS NOT NULL ORDER BY startFrame",
            [(bronze / "events_shots" / f"{MATCH}.parquet").as_posix()],
        ).fetchall()
    ]
    samples: list[Sample] = [
        (int(f), w / 1000.0, x * FT, y * FT, z * FT)
        for f, w, x, y, z in con.execute(
            "SELECT o.frameIdx, fr.wallClock, o.x, o.y, o.z FROM read_parquet(?) o "
            "JOIN read_parquet(?) fr USING (frameIdx) WHERE o.side = 'ball' AND o.z IS NOT NULL "
            "ORDER BY o.frameIdx",
            [
                (bronze / "tracking_objects" / f"{MATCH}.parquet").as_posix(),
                (bronze / "tracking_frames" / f"{MATCH}.parquet").as_posix(),
            ],
        ).fetchall()
    ]
    frames = [s[0] for s in samples]
    by_frame = {s[0]: s for s in samples}
    accepted, examples = 0, []
    for start in starts:
        i0 = bisect.bisect_left(frames, start + SEARCH_OFFSET)
        seg = samples[i0 : i0 + SEG_LEN]
        if len(seg) < SEG_LEN or _contig_len([s[0] for s in seg]) < MIN_CONTIG:
            continue
        if isinstance(_angles(seg[: _contig_len([s[0] for s in seg])]), str):
            continue
        accepted += 1
        flight: list[Sample] = []
        for f in range(start, start + SEG_LEN + SEARCH_OFFSET):
            if f not in by_frame:
                break
            flight.append(by_frame[f])
            apex = max(range(len(flight)), key=lambda i: flight[i][4])
            if len(flight) - 1 > apex and flight[-1][4] <= RIM_HEIGHT < flight[apex][4]:
                examples.append((start, len(flight) - 1))
                break
    print(
        f"probe entry {MATCH}: {len(starts)} made shots, {accepted} accepted by P3, "
        f"{len(examples)} with the ball at every frame from startFrame to the rim on the way down"
    )
    for start, k in examples:
        print(f"  startFrame {start}: rim reached {k} frames later")
    alive = complete and bool(examples)
    verdict = "VIVE" if alive else "MUERE"
    print(
        f"probe entry: {verdict} (quality.json complete for {len(table)} matches: {complete}; "
        f"examples in {MATCH}: {len(examples)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
