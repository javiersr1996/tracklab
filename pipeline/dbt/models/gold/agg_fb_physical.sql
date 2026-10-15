-- The season aggregate as bronze wrote it, one row per player, team and position group, minus the lineage
-- columns (`source_file`, `source_row`). `is_season_total` is constant false here: football has no season-total row (0 measured), the column exists so the six models share a shape.
SELECT
    * EXCLUDE (source_file, source_row),
    false AS is_season_total
FROM {{ source('bronze_football', 'aggregates_physical') }}
