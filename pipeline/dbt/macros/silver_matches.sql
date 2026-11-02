{#
  Task 127 (P16): the matches `frames` and `events` rebuild. The silver step of `tracklab
  build` passes the var `silver_matches` (`{"basketball": [114243], "football": []}`) with the
  matches whose inputs changed, and every bronze read of those two models keeps their rows only;
  the partitions of the other matches stay on disk untouched (`OVERWRITE_OR_IGNORE`). With no var,
  as in `--full`, in a plain `dbt build` and in CI, every match is built.

  The predicate goes on the bronze table, before any join or window: every computation of both
  models runs within one match (joins and windows are keyed by it), so a filtered build writes
  the same rows per partition as a full one (tests/incremental).
#}
{% macro silver_matches(sport, column) -%}
  {%- set matches = var('silver_matches', none) -%}
  {%- if matches is none -%}
    TRUE
  {%- else -%}
    {%- set ids = matches.get(sport, []) -%}
    {%- if ids -%}
      {{ column }} IN ({% for id in ids %}{{ id | int }}{% if not loop.last %}, {% endif %}{% endfor %})
    {%- else -%}
      FALSE
    {%- endif -%}
  {%- endif -%}
{%- endmacro %}
