-- (fact, value): the numbers lesson 2 prints.
SELECT 'rows' AS fact, count(*)::VARCHAR AS value FROM fb_physical
UNION ALL
SELECT 'over_98', count(*)::VARCHAR FROM fb_physical WHERE minutes_full_all > 98
UNION ALL
SELECT 'full_backs_over_98', count(*)::VARCHAR FROM fb_physical
WHERE position_group = 'Full Back' AND minutes_full_all > 98
UNION ALL
SELECT 'position_groups', count(DISTINCT position_group)::VARCHAR FROM fb_physical
UNION ALL
SELECT 'forwards_and_wide_over_100', count(*)::VARCHAR FROM fb_physical
WHERE position_group IN ('Center Forward', 'Wide Attacker') AND minutes_full_all > 100
UNION ALL
SELECT 'or_without_parentheses', count(*)::VARCHAR FROM fb_physical
WHERE position_group = 'Center Forward' OR position_group = 'Wide Attacker' AND minutes_full_all > 100
UNION ALL
SELECT 'timetohsr_null', count(*)::VARCHAR FROM fb_physical WHERE timetohsr_top3 IS NULL
UNION ALL
SELECT 'timetohsr_not_null', count(*)::VARCHAR FROM fb_physical WHERE timetohsr_top3 IS NOT NULL
UNION ALL
SELECT 'timetohsr_equals_null', count(*)::VARCHAR FROM fb_physical WHERE timetohsr_top3 = NULL
UNION ALL
SELECT 'max_matches_with_null_hsr', max(count_match)::VARCHAR FROM fb_physical
WHERE timetohsr_top3 IS NULL
UNION ALL
SELECT 'min_matches_with_hsr', min(count_match)::VARCHAR FROM fb_physical
WHERE timetohsr_top3 IS NOT NULL
