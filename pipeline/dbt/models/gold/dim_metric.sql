-- One row per (sport, family, metric) that has at least one non-null value in the
-- fact, so every fact row joins. `kind` is read off the name, in this order: the
-- literal suffix `_p30tip` (per 30 minutes of the team in possession), then a
-- token `pct` or `percentage`, `rate`, `ppp` or `per` (points per shot, drive or
-- pick), `distance` or `avgdistance`, `minutes`; anything else is a `count`
-- (which also holds some per-match averages of the physical table: the name
-- does not tell them apart). The list was written after counting the real names.

SELECT
    sport,
    family,
    metric,
    CASE
        WHEN ends_with(metric, '_p30tip') THEN 'per_30_tip'
        WHEN list_contains(string_split(metric, '_'), 'pct')
            OR list_contains(string_split(metric, '_'), 'percentage') THEN 'percentage'
        WHEN list_contains(string_split(metric, '_'), 'rate') THEN 'rate'
        WHEN list_contains(string_split(metric, '_'), 'ppp')
            OR list_contains(string_split(metric, '_'), 'per') THEN 'per_unit'
        WHEN list_contains(string_split(metric, '_'), 'distance')
            OR list_contains(string_split(metric, '_'), 'avgdistance') THEN 'distance'
        WHEN list_contains(string_split(metric, '_'), 'minutes') THEN 'minutes'
        ELSE 'count'
    END::VARCHAR AS kind
FROM (SELECT DISTINCT sport, family, metric FROM {{ ref('fact_player_season_metric') }})
