-- One row per player and sport across the six aggregates, keyed by the id the
-- provider gives (not rewritten through `player_id_aliases`: 8 of the alias ids
-- that appear in the basketball aggregates sit next to a row of their canonical
-- id in the same team, so a rewrite would break the grain). The name is the same
-- in every table (checked by the pytest of task 40); `short_name` is not: two
-- football players carry two spellings, and `max` picks one.

WITH players AS (
    SELECT 'basketball' AS sport, player_id, player_name, NULL AS short_name, NULL::DATE AS birthdate FROM {{ ref('agg_bb_shots') }}
    UNION ALL
    SELECT 'basketball', player_id, player_name, NULL, NULL FROM {{ ref('agg_bb_drives') }}
    UNION ALL
    SELECT 'basketball', player_id, player_name, NULL, NULL FROM {{ ref('agg_bb_picks') }}
    UNION ALL
    SELECT 'football', player_id, player_name, player_short_name, player_birthdate FROM {{ ref('agg_fb_obr') }}
    UNION ALL
    SELECT 'football', player_id, player_name, player_short_name, player_birthdate FROM {{ ref('agg_fb_passing') }}
    UNION ALL
    SELECT 'football', player_id, player_name, player_short_name, player_birthdate FROM {{ ref('agg_fb_physical') }}
)

SELECT
    sport::VARCHAR AS sport,
    player_id::BIGINT AS player_id,
    max(player_name)::VARCHAR AS player_name,
    max(short_name)::VARCHAR AS player_short_name,
    max(birthdate)::DATE AS player_birthdate
FROM players
GROUP BY sport, player_id
