# Silver schema

Columns and types below are read from `pipeline/dbt/target/catalog.json`, built by `cd pipeline && uv run dbt docs generate --project-dir dbt --profiles-dir dbt` over the real data in `pipeline/data` (not the CI fixtures). Descriptions and primary keys are read from `pipeline/dbt/models/silver/schema.yml` (a PK is a `unique` or `unique_combination` dbt test, never hand-typed). Row counts per sport are read from `pipeline/reports/stats_silver.csv`, the output of `tracklab stats`. The catalog has 10 model nodes: the 8 silver tables below plus the views `frame_possession` and `frames_attacking`; the two seeds are listed at the end. See `docs/decisions.md` for why the schema looks like this.

## `dim_sport`

The two rows that turn `sport` into a column. Every constant of a bundle that silver needs lives here once: the unit and its factor to metres, the sample rate, the semantics of the official clock, how many players are on the surface and which frame the provider's events arrive in.

Grain: one row per sport. PK: `sport or id_prefix [each independently unique]` (`dbt/models/silver/schema.yml`). Rows: 1 basketball / 1 football (`pipeline/reports/stats_silver.csv`).

| column | type | description |
|---|---|---|
| `sport` | VARCHAR |  |
| `id_prefix` | VARCHAR |  |
| `native_unit` | VARCHAR |  |
| `unit_to_m` | DOUBLE |  |
| `sample_rate_hz` | INTEGER |  |
| `clock_kind` | VARCHAR | countdown in basketball (600 -> 0), elapsed in football. |
| `players_on_surface` | INTEGER |  |
| `native_event_frame` | VARCHAR | The frame the provider's events arrive in, before silver rotates them to the venue frame. Measured by task 9 in both sports. |

## `dim_match`

One row per match, 20 in total, with the surface, the periods and the pinned commit.

Grain: one row per match. PK: `match_id` (`dbt/models/silver/schema.yml`). Rows: 10 basketball / 20 football (`pipeline/reports/stats_silver.csv`).

| column | type | description |
|---|---|---|
| `match_id` | VARCHAR |  |
| `sport` | VARCHAR |  |
| `native_match_id` | BIGINT |  |
| `competition` | VARCHAR |  |
| `season` | VARCHAR |  |
| `kickoff_utc` | TIMESTAMP |  |
| `home_team_id` | VARCHAR |  |
| `away_team_id` | VARCHAR |  |
| `home_score` | SMALLINT |  |
| `away_score` | SMALLINT |  |
| `surface_length_m` | DOUBLE |  |
| `surface_width_m` | DOUBLE |  |
| `surface_spec` | VARCHAR | fiba_28x15 in basketball, provider_<length>x<width> in football. |
| `n_periods` | SMALLINT | Counted from dim_period, never declared. 4 or 5 in basketball, 2 in football. |
| `z_ball_status` | VARCHAR |  |
| `z_player_status` | VARCHAR |  |
| `source_commit` | VARCHAR | The provider commit the bytes came from, read from the ingest manifest. |

## `dim_period`

One row per match and period. Football declares its boundaries in match.json; basketball's are read off the tracking, which is the only place its period changes.

Grain: one row per match and period. PK: `(match_id, period) [composite]` (`dbt/models/silver/schema.yml`). Rows: 41 basketball / 40 football (`pipeline/reports/stats_silver.csv`).

| column | type | description |
|---|---|---|
| `match_id` | VARCHAR |  |
| `period` | SMALLINT |  |
| `frame_native_start` | BIGINT |  |
| `frame_native_end` | BIGINT |  |
| `t_ms_start` | BIGINT |  |
| `t_ms_end` | BIGINT |  |
| `regulation_s` | INTEGER | What the competition gives the period, not what it lasted. |

## `dim_team`

One row per team, 30 in total (17 basketball, 13 football).

Grain: one row per team. PK: `team_id` (`dbt/models/silver/schema.yml`). Rows: 17 basketball / 13 football (`pipeline/reports/stats_silver.csv`).

| column | type | description |
|---|---|---|
| `team_id` | VARCHAR |  |
| `sport` | VARCHAR |  |
| `native_team_id` | BIGINT |  |
| `name` | VARCHAR |  |
| `short_name` | VARCHAR |  |

## `dim_team_period`

Task 9 in silver keys: which way each team attacks in each period, and the evidence that fixed it. Two rows per (match, period), opposite signs, asserted by tests/assert_attack_signs_opposite.sql.

Grain: one row per match, period and team. PK: `(match_id, period, team_id) [composite]` (`dbt/models/silver/schema.yml`). Rows: 82 basketball / 80 football (`pipeline/reports/stats_silver.csv`).

| column | type | description |
|---|---|---|
| `match_id` | VARCHAR |  |
| `period` | SMALLINT |  |
| `team_id` | VARCHAR |  |
| `attack_sign` | SMALLINT | +1 when that team attacks towards +x of the venue frame in that period. |
| `evidence` | VARCHAR |  |

## `dim_entity`

Everything that can hold a position in a match: both benches and the ball. Built from the roster, which covers every id the tracking uses in both sports and also the players who never left the bench.

Grain: one row per match and entity (player or ball). PK: `(match_id, entity_id) [composite]` (`dbt/models/silver/schema.yml`). Rows: 244 basketball / 739 football (`pipeline/reports/stats_silver.csv`).

| column | type | description |
|---|---|---|
| `match_id` | VARCHAR |  |
| `entity_id` | VARCHAR |  |
| `entity_kind` | VARCHAR |  |
| `team_id` | VARCHAR | NULL for the ball, which belongs to no team. |
| `native_entity_id` | BIGINT |  |
| `name` | VARCHAR |  |
| `jersey` | VARCHAR |  |
| `canonical_player_id` | VARCHAR |  |

## `frames`

The physical record of both sports in one shape: one row per match, native frame and entity, in metres and in the venue frame. Built from the tracking and from nothing else. Partitioned on disk by sport and native match id, because a silver match_id carries a colon and that is not a directory name on Windows.

Grain: one row per match, native frame and entity. PK: `(match_id, frame_native, entity_id) [composite]` (`dbt/models/silver/schema.yml`). Rows: 9,126,744 basketball / 20,213,849 football (`pipeline/reports/stats_silver.csv`).

| column | type | description |
|---|---|---|
| `match_id` | VARCHAR |  |
| `period` | SMALLINT | Never null; a frame outside every period does not reach silver. |
| `frame_native` | BIGINT |  |
| `t_ms` | BIGINT | frame_native x 1000 / sample_rate_hz, exact in both sports. |
| `clock_s` | DOUBLE | The official clock in its own semantics: counting down from 600 s in basketball, elapsed within the period in football. |
| `entity_id` | VARCHAR |  |
| `entity_kind` | VARCHAR |  |
| `team_id` | VARCHAR | NULL for the ball, which belongs to no team. |
| `x_m` | DOUBLE |  |
| `y_m` | DOUBLE |  |
| `z_m` | DOUBLE | NULL for every player in both sports (decision 6) and the provider's uncorrected value for the ball. assert_frames_z_only_on_the_ball.sql holds both halves of that. |
| `is_detected` | BOOLEAN | False means the provider extrapolated the position rather than seeing it. Almost everything that lands outside the surface is one of these. |
| `native_match_id` | BIGINT |  |
| `sport` | VARCHAR |  |

## `events`

Every event of both bundles in one shape: 20 native families in basketball, 4 plus the phases of play in football, and the football team possession this project derives. Coordinates are rotated to the venue frame, and a row whose rotation cannot be resolved carries none.

Grain: one row per match and event (native or derived). PK: `(match_id, event_id) [composite]` (`dbt/models/silver/schema.yml`). Rows: 71,984 basketball / 107,193 football (`pipeline/reports/stats_silver.csv`).

| column | type | description |
|---|---|---|
| `match_id` | VARCHAR |  |
| `event_id` | VARCHAR |  |
| `event_type` | VARCHAR | The conformed vocabulary; everything the seed does not name is `other`. |
| `native_family` | VARCHAR | What the provider calls this family, and how `other` is told apart. |
| `native_event_id` | VARCHAR |  |
| `native_subtype` | VARCHAR |  |
| `period` | SMALLINT |  |
| `frame_start` | BIGINT |  |
| `frame_end` | BIGINT |  |
| `t_ms_start` | BIGINT |  |
| `t_ms_end` | BIGINT |  |
| `team_id` | VARCHAR | NULL where the provider names no team, as in a basketball matchup. |
| `player_id` | VARCHAR |  |
| `player2_id` | VARCHAR |  |
| `x_start_m` | DOUBLE |  |
| `y_start_m` | DOUBLE |  |
| `x_end_m` | DOUBLE |  |
| `y_end_m` | DOUBLE |  |
| `possession_id` | VARCHAR | The event_id of the possession this event belongs to. NULL for the football events that fall between two team possessions. |
| `outcome` | VARCHAR |  |
| `native_match_id` | BIGINT |  |
| `sport` | VARCHAR |  |

## Views

### `frame_possession`

Which team possession a frame belongs to. A view, because expanding the possessions to their frames would write tens of millions of rows that are one range join away from what silver already holds.

Grain: one row per match and native frame that a team possession claims. PK: `(match_id, frame_native) [composite]` (`dbt/models/silver/schema.yml`). Rows: not tracked in `pipeline/reports/stats_silver.csv` (a view, not a silver table); see `pipeline/reports/contracts.json` (`rows_by_sport`) or `docs/decisions.md`.

| column | type | description |
|---|---|---|
| `sport` | VARCHAR |  |
| `match_id` | VARCHAR |  |
| `frame_native` | BIGINT |  |
| `possession_id` | VARCHAR |  |
| `team_id` | VARCHAR |  |

### `frames_attacking`

The frames of a team possession, turned so the team with the ball attacks towards +x: x_att_m = attack_sign * x_m. The only attack normalisation in silver. A frame no possession claims is absent, never given a guessed sign.

Grain: the rows of `frames` that a team possession claims, with two columns added. PK: no `unique`/`unique_combination` test declared (`dbt/models/silver/schema.yml`). Rows: not tracked in `pipeline/reports/stats_silver.csv` (a view, not a silver table); see `pipeline/reports/contracts.json` (`rows_by_sport`) or `docs/decisions.md`.

| column | type | description |
|---|---|---|
| `match_id` | VARCHAR |  |
| `period` | SMALLINT |  |
| `frame_native` | BIGINT |  |
| `t_ms` | BIGINT |  |
| `clock_s` | DOUBLE |  |
| `entity_id` | VARCHAR |  |
| `entity_kind` | VARCHAR |  |
| `team_id` | VARCHAR |  |
| `x_m` | DOUBLE |  |
| `y_m` | DOUBLE |  |
| `z_m` | DOUBLE |  |
| `is_detected` | BOOLEAN |  |
| `native_match_id` | BIGINT |  |
| `sport` | VARCHAR |  |
| `possession_id` | VARCHAR |  |
| `team_in_possession_id` | VARCHAR |  |
| `attack_sign` | SMALLINT |  |
| `x_att_m` | DOUBLE |  |
| `y_att_m` | DOUBLE |  |

## Seeds

### `surface_spec`

The surface specs a match can be played on, with their dimensions in metres. Two rows: the FIBA court task 9 measured, and the NBA court it rejected, kept so the rejection stays visible instead of disappearing into a WHERE clause. Football does not appear here because its pitch is declared per match by the provider.

| column | type | description |
|---|---|---|
| `surface_spec` | VARCHAR |  |
| `length_m` | DOUBLE |  |
| `width_m` | DOUBLE |  |
| `source` | VARCHAR |  |

### `event_type_map`

The conformed vocabulary, one row per (sport, native family, subtype pattern). A row with a literal subtype wins over the `*` of its family, which is how a football player_possession that ended in a pass becomes a `pass` while the rest stay `player_possession`.

| column | type | description |
|---|---|---|
| `sport` | VARCHAR |  |
| `native_family` | VARCHAR |  |
| `native_subtype_pattern` | VARCHAR |  |
| `event_type` | VARCHAR |  |
| `note` | VARCHAR |  |

Generated by a one-off script (`gen_schema_md.py`, not part of the `tracklab` package) reading `pipeline/dbt/target/catalog.json`, `pipeline/dbt/models/silver/schema.yml` and `pipeline/reports/stats_silver.csv` after `cd pipeline && uv run dbt docs generate --project-dir dbt --profiles-dir dbt`; re-run that command and the script to refresh this file.

