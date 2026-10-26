-- Field-goal percentage of the players with at least 300 attempts, in three ways.
SELECT player_name,
       mades / attempts AS ratio,
       mades // attempts AS whole_division,
       round(100.0 * mades / attempts, 1) AS fg_pct
FROM bb_shots
WHERE NOT is_season_total AND attempts >= 300
ORDER BY attempts DESC, player_name
LIMIT 8
