-- One row per non-null numeric cell of the six season aggregates, in long format:
-- (sport, family, player, team, position group, metric) -> value. It is what
-- Postgres loads (task 44) and the only layout where ordering by metric leaves
-- row groups to skip. `team_id` is NULL and `is_season_total` true on the
-- provider's season-total rows of basketball: filter them out before summing.

{{ agg_long(ref('agg_bb_shots'), 'basketball', 'shots', 'NULL') }}
UNION ALL
{{ agg_long(ref('agg_bb_drives'), 'basketball', 'drives', 'NULL') }}
UNION ALL
{{ agg_long(ref('agg_bb_picks'), 'basketball', 'picks', 'NULL') }}
UNION ALL
{{ agg_long(ref('agg_fb_obr'), 'football', 'obr', 'position_group') }}
UNION ALL
{{ agg_long(ref('agg_fb_passing'), 'football', 'passing', 'position_group') }}
UNION ALL
{{ agg_long(ref('agg_fb_physical'), 'football', 'physical', 'position_group') }}
