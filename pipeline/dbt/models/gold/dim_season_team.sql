-- One row per team and sport across the six aggregates. Named `dim_season_team`
-- and not `dim_team` because silver already has a `dim_team` (a different grain:
-- the teams of the 30 sample matches, 10 + 20, with the sport's prefix on the id), and dbt
-- model names are global. The basketball `total` row of a traded player is not a
-- team: it has a null `team_id` and is left out here.

WITH teams AS (
    SELECT 'basketball' AS sport, team_id, team_name FROM {{ ref('agg_bb_shots') }} WHERE NOT is_season_total
    UNION ALL
    SELECT 'basketball', team_id, team_name FROM {{ ref('agg_bb_drives') }} WHERE NOT is_season_total
    UNION ALL
    SELECT 'basketball', team_id, team_name FROM {{ ref('agg_bb_picks') }} WHERE NOT is_season_total
    UNION ALL
    SELECT 'football', team_id, team_name FROM {{ ref('agg_fb_obr') }}
    UNION ALL
    SELECT 'football', team_id, team_name FROM {{ ref('agg_fb_passing') }}
    UNION ALL
    SELECT 'football', team_id, team_name FROM {{ ref('agg_fb_physical') }}
)

SELECT
    sport::VARCHAR AS sport,
    team_id::BIGINT AS team_id,
    max(team_name)::VARCHAR AS team_name
FROM teams
GROUP BY sport, team_id
