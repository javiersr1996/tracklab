-- prompt: Among the football rows with a psv99 and at least 5 matches (count_match), find the two
--   fastest players of each position_group. Return position_group, player_name, psv99 and rn,
--   in that order, where rn is 1 for the highest psv99 of the group and 2 for the next one.
--   Break ties in psv99 by player_name, from A to Z. Order the rows by position_group (A to
--   Z) and then rn.
-- hint: row_number() OVER (PARTITION BY position_group ORDER BY psv99 DESC, player_name)
--   numbers the rows 1, 2, 3... inside each position_group.
-- hint: A window function cannot be used in WHERE. Compute rn in a subquery in FROM
--   (SELECT ... FROM (SELECT ..., row_number() ... AS rn FROM ...) AS t WHERE rn <= 2), or use the
--   QUALIFY clause, which filters on a window function the way HAVING filters groups.
-- hint: The inner query has the WHERE on psv99 and count_match, so the numbering only sees
--   the players of the pool; the outer query keeps rn <= 2 and sorts.
-- ordered: true
-- order_key: position_group, rn
SELECT position_group, player_name, psv99, rn
FROM (
  SELECT position_group, player_name, psv99,
         row_number() OVER (PARTITION BY position_group ORDER BY psv99 DESC, player_name) AS rn
  FROM fb_physical
  WHERE psv99 IS NOT NULL AND count_match >= 5
) AS t
WHERE rn <= 2
ORDER BY position_group, rn
