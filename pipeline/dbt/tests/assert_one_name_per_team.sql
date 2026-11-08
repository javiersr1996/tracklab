-- dim_team keeps `max(name)` per native team id, which silently picks one name
-- if a provider ever renames a team between matches. This turns the silent
-- pick into a failure: a team that carries two distinct trimmed names (or two
-- distinct short names) across the matches of its bundle is returned here.
-- Checked against bronze, not dim_team, because the GROUP BY in dim_team has
-- already collapsed the evidence.

-- depends_on: {{ ref('dim_team') }}

WITH sides AS (
    SELECT 'basketball' AS sport, home_team_id AS native_team_id,
           trim(home_team_name) AS name, NULL AS short_name
    FROM {{ source('bronze_basketball', 'matches') }}
    UNION ALL
    SELECT 'basketball', away_team_id, trim(away_team_name), NULL
    FROM {{ source('bronze_basketball', 'matches') }}
    UNION ALL
    SELECT 'football', home_team_id, trim(home_team_name), trim(home_team_short_name)
    FROM {{ source('bronze_football', 'match') }}
    UNION ALL
    SELECT 'football', away_team_id, trim(away_team_name), trim(away_team_short_name)
    FROM {{ source('bronze_football', 'match') }}
)

SELECT
    sport,
    native_team_id,
    count(DISTINCT name) AS n_names,
    count(DISTINCT short_name) AS n_short_names,
    string_agg(DISTINCT name, ' | ') AS names
FROM sides
GROUP BY sport, native_team_id
HAVING count(DISTINCT name) > 1 OR count(DISTINCT short_name) > 1
