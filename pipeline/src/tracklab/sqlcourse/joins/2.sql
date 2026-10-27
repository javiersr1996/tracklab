-- prompt: Which rows of fb_physical have no matching row in fb_passing? Match on player_id,
--   team_id and position_group. Return player_name, team_name and position_group, in that order.
--   Row order does not matter.
-- hint: A LEFT JOIN keeps every row of the left table; where the right table has no match, its
--   columns are NULL.
-- hint: Filter the joined rows on a right-table key IS NULL to keep only the rows with no match.
-- hint: FROM fb_physical AS p LEFT JOIN fb_passing AS q ON (the three equalities) WHERE
--   q.player_id IS NULL.
-- ordered: false
SELECT p.player_name, p.team_name, p.position_group
FROM fb_physical AS p
LEFT JOIN fb_passing AS q
  ON p.player_id = q.player_id
 AND p.team_id = q.team_id
 AND p.position_group = q.position_group
WHERE q.player_id IS NULL
