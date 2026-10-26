-- prompt: For the Auckland FC rows of fb_physical that have a matching row in fb_passing, return
--   player_name, position_group, sprint_count_full_all (from fb_physical) and pass_pct_completed
--   (from fb_passing), in that order. A row matches when player_id, team_id and position_group
--   are all equal. Row order does not matter.
-- hint: Give each table an alias (fb_physical AS p, fb_passing AS q) and write p.column or
--   q.column so it is clear where each value comes from.
-- hint: One key is not enough: a player can have one row per position_group, so the ON clause
--   needs the three equalities joined by AND.
-- hint: FROM fb_physical AS p JOIN fb_passing AS q ON p.player_id = q.player_id AND p.team_id =
--   q.team_id AND p.position_group = q.position_group WHERE p.team_name = 'Auckland FC'.
-- ordered: false
SELECT p.player_name, p.position_group, p.sprint_count_full_all, q.pass_pct_completed
FROM fb_physical AS p
JOIN fb_passing AS q
  ON p.player_id = q.player_id
 AND p.team_id = q.team_id
 AND p.position_group = q.position_group
WHERE p.team_name = 'Auckland FC'
