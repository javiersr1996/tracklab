"""dim_match takes `source_commit` from the manifest, one row per match.

Task 57 added a second football source (opendata-bodypose) and the join on `sport` doubled every
football match: CI failed on `unique_dim_match_match_id`. dbt is not run by pytest, so this runs
the model's own `commits` CTE and its final join, read from the SQL file, against the real
manifest.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

PIPELINE = Path(__file__).resolve().parents[2]
MODEL = PIPELINE / "dbt" / "models" / "silver" / "dim_match.sql"
MANIFEST = PIPELINE / "manifest" / "sources.json"


def test_each_sport_joins_exactly_one_commit() -> None:
    sql = MODEL.read_text(encoding="utf-8")
    cte = re.search(r"commits AS \((.*?)\n\),", sql, re.S)
    on = re.search(r"JOIN commits c ON (.+)", sql)
    assert cte is not None and on is not None
    cte_sql = cte.group(1).replace(
        "{{ source('manifest', 'sources') }}", f"read_json('{MANIFEST.as_posix()}')"
    )
    rows = (
        duckdb.connect()
        .execute(
            f"WITH commits AS ({cte_sql}) "
            f"SELECT m.sport, count(*) FROM (VALUES ('football'), ('basketball')) m(sport) "
            f"JOIN commits c ON {on.group(1)} GROUP BY ALL ORDER BY 1"
        )
        .fetchall()
    )
    assert rows == [("basketball", 1), ("football", 1)]
