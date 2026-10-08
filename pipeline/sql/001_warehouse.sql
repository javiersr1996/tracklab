-- Task 44 (P4): the gold dimensional model in Postgres, loaded by `tracklab load postgres`.
-- Applied once per database, inside the loader's transaction, and recorded with its sha256 in
-- warehouse.schema_migrations: a change goes in a new numbered file, never in this one.
-- Needs Postgres 15 or later (UNIQUE NULLS NOT DISTINCT). Every table carries `row_hash`, the
-- fingerprint the loader compares to find what changed (decision 8 of tasks/todo.md). Text columns
-- use the C collation: byte order, the same on any server whatever its locale, and the loader's
-- joins sort them several times faster than with a language collation.

CREATE TABLE warehouse.dim_player (
    sport text COLLATE "C" NOT NULL,
    player_id bigint NOT NULL,
    player_name text COLLATE "C" NOT NULL,
    player_short_name text COLLATE "C",
    player_birthdate date,
    row_hash bytea NOT NULL,
    PRIMARY KEY (sport, player_id)
);

-- Gold `dim_season_team`: the teams of the season aggregates. The basketball row of a traded
-- player's season total is not a team, so it is not here.
CREATE TABLE warehouse.dim_team (
    sport text COLLATE "C" NOT NULL,
    team_id bigint NOT NULL,
    team_name text COLLATE "C" NOT NULL,
    row_hash bytea NOT NULL,
    PRIMARY KEY (sport, team_id)
);

CREATE TABLE warehouse.dim_metric (
    sport text COLLATE "C" NOT NULL,
    family text COLLATE "C" NOT NULL,
    metric text COLLATE "C" NOT NULL,
    kind text COLLATE "C" NOT NULL,
    row_hash bytea NOT NULL,
    PRIMARY KEY (sport, family, metric)
);

-- One row per non-null numeric cell of the six season aggregates. `team_id` is NULL (and
-- `is_season_total` true) on the basketball season-total rows of traded players, and
-- `position_group` is NULL in basketball: the grain has two nullable columns, so it is a unique
-- constraint with NULLS NOT DISTINCT instead of a primary key. Its index leads with (sport,
-- family, metric), the filter of the example queries.
CREATE TABLE warehouse.fact_player_season_metric (
    sport text COLLATE "C" NOT NULL,
    family text COLLATE "C" NOT NULL,
    metric text COLLATE "C" NOT NULL,
    player_id bigint NOT NULL,
    team_id bigint,
    position_group text COLLATE "C",
    is_season_total boolean NOT NULL,
    value double precision NOT NULL,
    row_hash bytea NOT NULL,
    CONSTRAINT fact_player_season_metric_grain UNIQUE NULLS NOT DISTINCT
        (sport, family, metric, player_id, team_id, position_group, is_season_total),
    FOREIGN KEY (sport, player_id) REFERENCES warehouse.dim_player,
    FOREIGN KEY (sport, team_id) REFERENCES warehouse.dim_team,
    FOREIGN KEY (sport, family, metric) REFERENCES warehouse.dim_metric
);

-- One player's rows: the profile example, and the foreign key check when a player leaves
-- dim_player (without it, a scan of the whole fact per player removed).
CREATE INDEX fact_player_season_metric_player
    ON warehouse.fact_player_season_metric (sport, player_id);

-- One row per table and load: what the incremental load wrote.
CREATE TABLE warehouse.load_log (
    loaded_at timestamptz NOT NULL,
    table_name text NOT NULL,
    inserted integer NOT NULL,
    updated integer NOT NULL,
    deleted integer NOT NULL,
    unchanged integer NOT NULL,
    PRIMARY KEY (loaded_at, table_name)
);

-- The role the web reads with (task 45). It can read this schema and nothing else: no write
-- privilege anywhere, so a transaction opened READ WRITE still cannot change a row. In this
-- database its sessions start read-only and cancel any statement after 2 s (the time limit of
-- decision 7, a hypothesis). Roles belong to the cluster, not the database: it is created only
-- once, without LOGIN (`tracklab load postgres --reader-password-env` gives it a password), and
-- its settings are tied to this database, so they live and go with it.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'warehouse_reader') THEN
        CREATE ROLE warehouse_reader NOLOGIN;
    END IF;
    EXECUTE format('ALTER ROLE warehouse_reader IN DATABASE %I SET statement_timeout = %L',
                   current_database(), '2s');
    EXECUTE format('ALTER ROLE warehouse_reader IN DATABASE %I SET default_transaction_read_only = on',
                   current_database());
    EXECUTE format('ALTER ROLE warehouse_reader IN DATABASE %I SET search_path = warehouse',
                   current_database());
END
$$;
GRANT USAGE ON SCHEMA warehouse TO warehouse_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA warehouse TO warehouse_reader;
