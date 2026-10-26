-- prompt: For midfielders with at least 20 matches (count_match) return player_name,
--   sprints_per_90 and speed_band, in that order. sprints_per_90 is 90 * sprint_count_full_all /
--   minutes_full_all rounded to 2 decimals. speed_band is 'fast' when psv99 is 28 or more,
--   'medium' when it is 27 or more (and under 28), and 'slow' otherwise. Row order does not
--   matter.
-- hint: A computed column is an expression plus an alias: round(90 * ... / ..., 2) AS
--   sprints_per_90.
-- hint: CASE tries its WHEN branches from the top and stops at the first true one, so the 28
--   test goes before the 27 test; ELSE catches the rest.
-- hint: CASE WHEN psv99 >= 28 THEN 'fast' WHEN psv99 >= 27 THEN 'medium' ELSE 'slow' END AS
--   speed_band.
-- ordered: false
SELECT player_name,
       round(90 * sprint_count_full_all / minutes_full_all, 2) AS sprints_per_90,
       CASE WHEN psv99 >= 28 THEN 'fast' WHEN psv99 >= 27 THEN 'medium' ELSE 'slow' END
         AS speed_band
FROM fb_physical
WHERE position_group = 'Midfield' AND count_match >= 20
