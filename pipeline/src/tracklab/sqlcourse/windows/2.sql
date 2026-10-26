-- prompt: Percentile of speed inside a position, the way /warehouse prints it. Take the football
--   rows with a psv99 and at least 5 matches (count_match); for each, the percentile is
--   100 * percent_rank() over the rows of its position_group ordered by psv99 from low to high,
--   rounded to 1 decimal. Return player_name, position_group, psv99 and percentile (the rounded
--   value), in that order, for the Full Backs whose percentile is 90 or above, compared before
--   rounding, highest percentile first. Break ties by player_name, from A to Z.
-- hint: percent_rank() OVER (PARTITION BY position_group ORDER BY psv99) is 0 for the lowest
--   value of a group and 1 for the highest.
-- hint: The window only sees rows that passed the WHERE inside its own query: put the pool
--   conditions (psv99 and count_match) in the inner query, and the position and the 90 in the
--   outer one.
-- hint: Inner: 100 * percent_rank() OVER (...) AS raw. Outer: WHERE position_group = 'Full
--   Back' AND raw >= 90, SELECT round(raw, 1) AS percentile, ORDER BY percentile DESC,
--   player_name.
-- ordered: true
-- order_key: percentile DESC, player_name
SELECT player_name, position_group, psv99, round(raw, 1) AS percentile
FROM (
  SELECT player_name, position_group, psv99,
         100 * percent_rank() OVER (PARTITION BY position_group ORDER BY psv99) AS raw
  FROM fb_physical
  WHERE psv99 IS NOT NULL AND count_match >= 5
) AS pool
WHERE position_group = 'Full Back' AND raw >= 90
ORDER BY percentile DESC, player_name
