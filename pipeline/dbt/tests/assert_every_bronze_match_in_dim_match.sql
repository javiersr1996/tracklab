-- Every match bronze holds is in dim_match. dim_match joins each match to its orientation report,
-- its court seed, its periods and its source commit with INNER JOINs, so a match missing from any of
-- them vanishes from dim_match, and with it from every fact that joins through it (frames, events),
-- without any model failing. The rows returned are the matches that went missing.

WITH bronze AS (
    SELECT 'basketball' AS sport, m.id AS native_match_id
    FROM {{ source('bronze_basketball', 'matches') }} m
    UNION ALL
    SELECT 'football' AS sport, f.id AS native_match_id
    FROM {{ source('bronze_football', 'match') }} f
)

SELECT b.sport, b.native_match_id
FROM bronze b
JOIN {{ ref('dim_sport') }} s ON s.sport = b.sport
LEFT JOIN {{ ref('dim_match') }} d ON d.match_id = s.id_prefix || ':' || b.native_match_id
WHERE d.match_id IS NULL
