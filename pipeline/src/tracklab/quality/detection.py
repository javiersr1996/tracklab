"""How often the provider says it saw each kind of object, per match.

`is_detected` false means the position was extrapolated, not seen. The share is
read per sport, match and entity kind straight off silver `frames`; nothing is
filtered, so a kind the provider never marks as seen shows up as 0%.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from tracklab.quality.common import Result
from tracklab.silver.stats import table_glob

CHECK = "detection"


def detection(data_dir: Path, reports_dir: Path) -> list[Result]:
    # `reports_dir` is unused: unlike `partitions`, this check reads only silver.
    rows = (
        duckdb.connect()
        .execute(
            """
            SELECT sport, match_id, entity_kind,
                   count(*) FILTER (WHERE is_detected) AS detected, count(*) AS n
            FROM read_parquet(?)
            GROUP BY ALL
            """,
            [table_glob(data_dir, "frames")],
        )
        .fetchall()
    )
    return [
        Result(
            check=CHECK,
            sport=str(sport),
            match_id=str(match_id),
            metric=f"{kind}_detected_pct",
            value=round(100.0 * int(detected) / int(n), 4),
            unit="%",
            n=int(n),
        )
        for sport, match_id, kind, detected, n in rows
    ]
