-- prompt: For team rows (is_season_total is false) with at least 400 total_points, return
--   player_name, total_points, games_played and whole_ppg, in that order. whole_ppg is the points
--   per game with the decimals cut off (12.9 becomes 12): use integer division. Row order does
--   not matter.
-- hint: / divides with decimals, so 12.9 stays 12.9 and ROUND would turn it into 13.
-- hint: // is the integer division of DuckDB: 7 // 2 is 3.
-- hint: total_points // games_played, with WHERE NOT is_season_total AND total_points >= 400.
-- ordered: false
SELECT player_name, total_points, games_played, total_points // games_played AS whole_ppg
FROM bb_shots
WHERE NOT is_season_total AND total_points >= 400
