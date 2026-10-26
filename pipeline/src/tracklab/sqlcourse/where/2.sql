-- prompt: List the central defenders and full backs who played in at least 20 matches
--   (count_match). Return player_name, team_name, position_group and count_match, in that order.
--   Row order does not matter.
-- hint: At least 20 means 20 or more: count_match >= 20, not count_match > 20.
-- hint: Two positions and one condition on matches: AND binds tighter than OR, so
--   parentheses around the two positions keep the matches condition on both.
-- ordered: false
SELECT player_name, team_name, position_group, count_match
FROM fb_physical
WHERE (position_group = 'Central Defender' OR position_group = 'Full Back')
  AND count_match >= 20
