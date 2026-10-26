-- prompt: Which center forwards have no value in timetohsr_top3 but played in at least 2
--   matches (count_match)? Return player_name, team_name and count_match, in that order. Row
--   order does not matter.
-- hint: A missing value is NULL, and nothing is equal to NULL, not even NULL: timetohsr_top3 = NULL
--   never matches a row.
-- hint: Test for it with IS NULL, and combine it with the other two conditions using AND.
-- ordered: false
SELECT player_name, team_name, count_match
FROM fb_physical
WHERE position_group = 'Center Forward' AND timetohsr_top3 IS NULL AND count_match >= 2
