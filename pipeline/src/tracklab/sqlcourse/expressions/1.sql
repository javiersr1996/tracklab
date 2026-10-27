-- prompt: Among the team rows (is_season_total is false) of players with fewer than 4 attempts,
--   return player_name, attempts, mades and fg_pct, in that order. fg_pct is 100 * mades /
--   attempts rounded to 1 decimal, and it must be NULL (not an error or an infinity) when the
--   player has 0 attempts. Row order does not matter.
-- hint: In DuckDB, mades / attempts is a division with decimals, and a division by 0 does not
--   fail: it gives infinity or NaN, which is not a percentage.
-- hint: NULLIF(attempts, 0) turns a 0 into NULL, and anything divided by NULL is NULL.
-- hint: round(100.0 * mades / NULLIF(attempts, 0), 1), with WHERE NOT is_season_total AND
--   attempts < 4.
-- ordered: false
SELECT player_name, attempts, mades,
       round(100.0 * mades / NULLIF(attempts, 0), 1) AS fg_pct
FROM bb_shots
WHERE NOT is_season_total AND attempts < 4
