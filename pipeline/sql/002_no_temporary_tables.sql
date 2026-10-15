-- Review V of P4 (M1): what 001 left open to the read-only role. Read only is the role's default,
-- not a wall: warehouse_reader can open a read-write transaction and, without a privilege on any
-- table of `warehouse`, still create temporary tables, because PUBLIC holds TEMPORARY on every
-- database. This takes it from PUBLIC; the owner, who runs the load and stages it in temporary
-- tables, keeps its own.
--
-- Two holes stay open, because closing them needs a superuser, which Neon does not give: any
-- role can write large objects (`lo_from_bytea`), and any role can change its own defaults in
-- the database (`ALTER ROLE ... IN DATABASE ... SET statement_timeout = 0`), so the 2 s and the
-- read-only default of 001 last only until the role changes them. The route of /warehouse does
-- not rely on either: it runs each query in a READ ONLY transaction with its own
-- `SET LOCAL statement_timeout` (web/lib/warehouse/pg-run.ts).
DO $$
BEGIN
    EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
END
$$;
