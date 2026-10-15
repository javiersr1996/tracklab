-- The season aggregate as bronze wrote it, one row per player and team, minus the lineage
-- columns (`source_file`, `source_row`). `is_season_total` marks the provider's season-total row of a traded player (`team_name = 'total'`, null `team_id`): summing rows without filtering it counts that player twice.
SELECT
    * EXCLUDE (source_file, source_row),
    (team_name = 'total') AS is_season_total
FROM {{ source('bronze_basketball', 'aggregates_shots') }}
