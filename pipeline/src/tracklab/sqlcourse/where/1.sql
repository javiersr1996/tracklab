-- prompt: Which wide attackers and center forwards have a minutes_full_all above 100? Return
--   player_name, position_group and minutes_full_all, in that order. Row order does not matter.
-- hint: position_group holds the position as text, so each position is a comparison with
--   quotes: position_group = 'Center Forward'.
-- hint: OR joins the two positions and AND adds the minutes; AND is applied before OR, so put
--   the two positions in parentheses.
-- hint: WHERE (position_group = 'Center Forward' OR position_group = 'Wide Attacker') AND
--   minutes_full_all > 100. IN ('Center Forward', 'Wide Attacker') says the same, shorter.
-- ordered: false
SELECT player_name, position_group, minutes_full_all
FROM fb_physical
WHERE position_group IN ('Center Forward', 'Wide Attacker') AND minutes_full_all > 100
