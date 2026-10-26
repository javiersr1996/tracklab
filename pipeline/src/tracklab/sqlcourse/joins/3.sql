-- prompt: Which rows of fb_passing have no matching row in fb_physical? Match on player_id,
--   team_id and position_group. Return player_name, team_name and position_group, in that order,
--   ordered by team_name and then player_name, both from A to Z.
-- hint: It is the same shape as the previous exercise with the tables swapped: start from
--   fb_passing and LEFT JOIN fb_physical.
-- hint: The ORDER BY goes last, after WHERE: ORDER BY team_name, player_name.
-- hint: FROM fb_passing AS q LEFT JOIN fb_physical AS p ON (the three equalities) WHERE
--   p.player_id IS NULL ORDER BY q.team_name, q.player_name.
-- ordered: true
-- order_key: team_name, player_name
SELECT q.player_name, q.team_name, q.position_group
FROM fb_passing AS q
LEFT JOIN fb_physical AS p
  ON p.player_id = q.player_id
 AND p.team_id = q.team_id
 AND p.position_group = q.position_group
WHERE p.player_id IS NULL
ORDER BY q.team_name, q.player_name
