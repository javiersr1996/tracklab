-- Example "profile" of /warehouse, on the dimensional model: one basketball player's season line
-- from the team rows (never the traded players' total row), the long fact pivoted back to the
-- columns of bb_shots.
SELECT p.player_name,
       t.team_name,
       (max(f.value) FILTER (WHERE f.metric = 'games_played'))::bigint AS games_played,
       (max(f.value) FILTER (WHERE f.metric = 'attempts'))::bigint AS attempts,
       (max(f.value) FILTER (WHERE f.metric = 'mades'))::bigint AS mades,
       (max(f.value) FILTER (WHERE f.metric = 'three_attempts'))::bigint AS three_attempts,
       (max(f.value) FILTER (WHERE f.metric = 'three_mades'))::bigint AS three_mades,
       (max(f.value) FILTER (WHERE f.metric = 'total_points'))::bigint AS total_points,
       round((max(f.value) FILTER (WHERE f.metric = 'total_points')
              / max(f.value) FILTER (WHERE f.metric = 'games_played'))::numeric, 1)
           AS points_per_game
FROM warehouse.fact_player_season_metric AS f
JOIN warehouse.dim_player AS p ON p.sport = f.sport AND p.player_id = f.player_id
JOIN warehouse.dim_team AS t ON t.sport = f.sport AND t.team_id = f.team_id
WHERE f.sport = 'basketball' AND f.family = 'shots' AND NOT f.is_season_total
  AND f.metric IN ('games_played', 'attempts', 'mades', 'three_attempts', 'three_mades',
                   'total_points')
  AND p.player_name = {profile_player}
GROUP BY p.player_name, t.team_name, f.player_id, f.team_id
