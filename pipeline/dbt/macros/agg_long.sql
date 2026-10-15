{#
  One wide season aggregate in long format: one row per player, team (and
  position group in football) and numeric metric, NULL cells dropped. The metric
  columns are the BIGINT and DOUBLE ones that are not an id, read from the
  relation at run time, so a column the provider adds shows up without editing
  six lists. UNPIVOT drops NULLs by default, which is what "one row per non-null
  cell" means; the pytest that checks the total counts the cells another way.
#}
{% macro agg_long(rel, sport, family, position_group) %}
{%- if execute -%}
{%- set not_metric = ['competition_edition_id', 'competition_id', 'season_id', 'player_id', 'team_id'] -%}
{%- set metrics = [] -%}
{%- for col in adapter.get_columns_in_relation(rel) -%}
    {%- if col.dtype in ['BIGINT', 'DOUBLE'] and col.name not in not_metric and col.name != 'source_row' -%}
        {%- do metrics.append('"' ~ col.name ~ '"') -%}
    {%- endif -%}
{%- endfor -%}
SELECT
    '{{ sport }}'::VARCHAR AS sport,
    '{{ family }}'::VARCHAR AS family,
    player_id::BIGINT AS player_id,
    team_id::BIGINT AS team_id,
    {{ position_group }}::VARCHAR AS position_group,
    is_season_total,
    metric::VARCHAR AS metric,
    value::DOUBLE AS value
FROM (
    UNPIVOT (
        SELECT player_id, team_id, {% if position_group != 'NULL' %}position_group, {% endif %}is_season_total, {{ metrics | join(', ') }}
        FROM {{ rel }}
    )
    ON {{ metrics | join(', ') }}
    INTO NAME metric VALUE value
)
{%- else -%}
SELECT 1
{%- endif -%}
{% endmacro %}
