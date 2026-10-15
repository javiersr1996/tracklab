-- Every fact row has its player, its metric and, unless it is a season-total row,
-- its team. LEFT JOINs that keep the orphans: an INNER JOIN would drop them and
-- the test would pass by construction.
SELECT f.sport, f.family, f.player_id, f.team_id, f.metric
FROM {{ ref('fact_player_season_metric') }} f
LEFT JOIN {{ ref('dim_player') }} p ON p.sport = f.sport AND p.player_id = f.player_id
LEFT JOIN {{ ref('dim_metric') }} m ON m.sport = f.sport AND m.family = f.family AND m.metric = f.metric
LEFT JOIN {{ ref('dim_season_team') }} t ON t.sport = f.sport AND t.team_id = f.team_id
WHERE p.player_id IS NULL
   OR m.metric IS NULL
   OR (NOT f.is_season_total AND t.team_id IS NULL)
   OR (f.is_season_total AND f.team_id IS NOT NULL)
