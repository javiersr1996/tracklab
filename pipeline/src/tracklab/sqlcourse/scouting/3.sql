-- prompt: Basketball scouting from two tables. Using team rows only (is_season_total is false)
--   with at least 10 games_played, find the players with at least 12 points per game
--   (bb_shots: total_points / games_played) and at least 6 drives per game (bb_drives:
--   total_drives / games_played). Match the tables on player_id and team_id. Return
--   player_name, team_name, points_per_game and drives_per_game (both rounded to 1 decimal), in
--   that order. Row order does not matter.
-- hint: One CTE per table, each computing its per-game rate; divide with a decimal, as in
--   total_points * 1.0 / games_played.
-- hint: Put the rates unrounded in the WHERE and round only in the SELECT, so a value like
--   11.96 does not pass as 12.
-- hint: WITH scoring AS (SELECT player_id, team_id, player_name, team_name, total_points * 1.0 /
--   games_played AS ppg FROM bb_shots WHERE ...), driving AS (...) SELECT ... FROM scoring JOIN
--   driving USING (player_id, team_id) WHERE ppg >= 12 AND dpg >= 6.
-- ordered: false
WITH scoring AS (
  SELECT player_id, team_id, player_name, team_name,
         total_points * 1.0 / games_played AS ppg
  FROM bb_shots
  WHERE NOT is_season_total AND games_played >= 10
),
driving AS (
  SELECT player_id, team_id, total_drives * 1.0 / games_played AS dpg
  FROM bb_drives
  WHERE NOT is_season_total AND games_played >= 10
)
SELECT s.player_name, s.team_name, round(s.ppg, 1) AS points_per_game,
       round(d.dpg, 1) AS drives_per_game
FROM scoring AS s
JOIN driving AS d ON s.player_id = d.player_id AND s.team_id = d.team_id
WHERE s.ppg >= 12 AND d.dpg >= 6
