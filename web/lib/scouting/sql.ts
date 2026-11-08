// The SQL of /warehouse/scouting (task 135), built from the catalog in `scouting.json` and from
// nothing the visitor types: every identifier comes out of the catalog (and is checked to be a
// plain lowercase name), the ids of a comparison must be integers, and a position group must be
// one the catalog lists. The result goes through `checkSql` before it reaches the engine.
//
// Percentiles are what `tracklab publish scouting` writes: `percent_rank()` ascending times 100,
// one decimal, inside the pool of the metric, which is the rows that pass the sample floor, in
// their position group in football (the league in basketball), with a value that is not null (a
// NULL gets no percentile and does not move anyone else's: the window is also partitioned by
// `value IS NULL`). Rounding is half up on the exact fraction, as the producer does: DuckDB's
// `round(100 * x, 1)` on a double lands either side of a tie (153/240 gave 63.7, exact 63.75
// rounds to 63.8), so the percentile is floor(x * 1000 + 0.5) / 10 with 1e-6 for float noise (two
// distinct values of x * 1000 are at least 1/(2 * (n - 1)) from a .5, far more than that). A high percentile is a high value, not a verdict.

import { checkSql } from "../warehouse/sql";

export interface ScoutingMetric {
  id: string;
  // A column, or `column / games_played`.
  expr: string;
  label: string;
  scale: string;
  unit: string;
}

export interface ScoutingTable {
  table: string;
  sport: string;
  key: string[];
  sample: string;
  floor: string;
  partition: string | null;
  metrics: ScoutingMetric[];
  pools: { group: string | null }[];
}

export interface ScoutingCatalog {
  age_reference: string;
  tables: ScoutingTable[];
}

// A player row as the page names it: `position_group` only in football.
export interface PlayerKey {
  player_id: number;
  team_id: number;
  position_group?: string;
}

const NAME = /^[a-z][a-z0-9_]*$/;
const EXPR = /^[a-z][a-z0-9_]*( \/ games_played)?$/;
const FLOOR = /^(NOT is_season_total AND )?([a-z][a-z0-9_]*) >= \d{1,4}$/;
const GROUP = /^[A-Za-z][A-Za-z ]*$/;

function name(value: string, what: string): string {
  if (!NAME.test(value)) throw new Error(`scouting catalog: ${what} ${JSON.stringify(value)} is not a plain name`);
  return value;
}

function integer(value: unknown, what: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${what} must be a non-negative integer`);
  }
  return value;
}

function floorSql(t: ScoutingTable): string {
  const m = FLOOR.exec(t.floor);
  if (!m || m[2] !== t.sample) throw new Error(`scouting catalog: floor ${JSON.stringify(t.floor)} of ${t.table}`);
  return t.floor;
}

function exprSql(m: ScoutingMetric): string {
  if (!EXPR.test(m.expr)) throw new Error(`scouting catalog: expression ${JSON.stringify(m.expr)}`);
  name(m.id, "metric id");
  return m.expr;
}

function find(catalog: ScoutingCatalog, table: string): ScoutingTable {
  const t = catalog.tables.find((c) => c.table === table);
  if (!t) throw new Error(`${JSON.stringify(table)} is not a table of the scouting catalog`);
  name(t.table, "table");
  return t;
}

function pick(t: ScoutingTable, ids: readonly string[] | undefined): ScoutingMetric[] {
  if (ids === undefined) return t.metrics;
  return ids.map((id) => {
    const m = t.metrics.find((c) => c.id === id);
    if (!m) throw new Error(`${JSON.stringify(id)} is not a metric of ${t.table}`);
    return m;
  });
}

// `<out>` holds the value and `<out>_pctl` its percentile (NULL when the value is).
// With `counts`, `<out>_n` is the rows of the pool with a value for the metric.
function metricColumns(
  t: ScoutingTable,
  metrics: ScoutingMetric[],
  out: (id: string) => string,
  counts = false,
): string[] {
  return metrics.flatMap((m) => {
    const e = exprSql(m);
    const part = [...(t.partition ? [name(t.partition, "partition")] : []), `((${e}) IS NULL)`].join(", ");
    const rank = `floor(percent_rank() OVER (PARTITION BY ${part} ORDER BY (${e})) * 1000 + 0.5 + 1e-6) / 10`;
    const columns = [`(${e}) AS ${out(m.id)}`, `CASE WHEN (${e}) IS NULL THEN NULL ELSE ${rank} END AS ${out(m.id)}_pctl`];
    if (counts) {
      const by = t.partition ? `PARTITION BY ${name(t.partition, "partition")}` : "";
      columns.push(`count(${e}) OVER (${by}) AS ${out(m.id)}_n`);
    }
    return columns;
  });
}

// One window per metric over the rows of one table that pass its floor.
function poolSelect(
  t: ScoutingTable,
  metrics: ScoutingMetric[],
  head: string[],
  out: (id: string) => string,
  counts = false,
): string {
  const key = t.key.map((k) => name(k, "key column"));
  return `SELECT ${[...key, ...head, ...metricColumns(t, metrics, out, counts)].join(", ")} FROM ${t.table} WHERE ${floorSql(t)}`;
}

// The table of one catalog table: one row per key that passes the floor, in the order of the
// name. Columns: the key, `player_name`, `team_name`, `sample` (the floor's column), `age` in
// football, then `<id>` and `<id>_pctl` for each metric.
export function tableSql(catalog: ScoutingCatalog, table: string, metricIds?: readonly string[]): string {
  const t = find(catalog, table);
  const head = ["player_name", "team_name", `${name(t.sample, "sample")} AS sample`];
  if (t.sport === "football") head.push(`player_age AS age`);
  const inner = poolSelect(t, pick(t, metricIds), head, (id) => id);
  return gate(`SELECT * FROM (${inner}) ORDER BY player_name, ${t.key.join(", ")}`, catalog);
}

// The comparison of two players over every table of a sport. Each table's percentiles are
// computed inside its own pool first (a CTE with its floor and its windows) and the two rows are
// picked out afterwards by the whole key: ranking after the join would rank inside the
// intersection of the pools. A player under a table's floor keeps NULL for its metrics and
// `<table>_below_floor` true. Columns: `slot` (0 the first player, 1 the second), the key,
// `player_name`, `team_name`, `age` in football, then per table `<table>_below_floor`,
// `<table>__<id>`, `<table>__<id>_pctl` and `<table>__<id>_n` (the metric's pool, counted by the engine).
export function compareSql(
  catalog: ScoutingCatalog,
  sport: string,
  players: readonly [PlayerKey, PlayerKey],
): string {
  const tables = catalog.tables.filter((t) => t.sport === sport);
  if (tables.length === 0) throw new Error(`${JSON.stringify(sport)} is not a sport of the scouting catalog`);
  const first = tables[0];
  const key = first.key.map((k) => name(k, "key column"));
  const groups = new Set(tables.flatMap((t) => t.pools.map((p) => p.group)).filter((g) => g !== null));
  const literal = (p: PlayerKey, column: string): string => {
    if (column === "position_group") {
      const g = p.position_group;
      if (typeof g !== "string" || !GROUP.test(g) || !groups.has(g)) {
        throw new Error("position_group is not one of the catalog's groups");
      }
      return `'${g}'`;
    }
    if (column !== "player_id" && column !== "team_id") throw new Error(`key column ${column} is not an id`);
    return String(integer(p[column], column));
  };

  const values = players.map((p, slot) => `(${[slot, ...key.map((k) => literal(p, k))].join(", ")})`);
  const ctes = [`k(slot, ${key.join(", ")}) AS (VALUES ${values.join(", ")})`];
  const on = (alias: string) => key.map((c) => `${alias}.${c} = k.${c}`).join(" AND ");

  // Name, team and age come from the first table, whether or not the player passes its floor.
  const football = sport === "football";
  const nameCols = ["player_name", "team_name", ...(football ? [`player_age AS age`] : [])];
  ctes.push(`n AS (SELECT ${[...key, ...nameCols].join(", ")} FROM ${first.table})`);

  const select = ["k.slot", ...key.map((c) => `k.${c}`), "n.player_name", "n.team_name", ...(football ? ["n.age"] : [])];
  const joins = [`LEFT JOIN n ON ${on("n")}`];
  tables.forEach((t, i) => {
    const alias = `c${i}`;
    const out = (id: string) => `${name(t.table, "table")}__${id}`;
    const inner = poolSelect(t, t.metrics, [], out, true);
    const only = key.map((c) => `${c} IN (SELECT ${c} FROM k)`).join(" AND ");
    ctes.push(`${alias} AS (SELECT * FROM (${inner}) WHERE ${only})`);
    joins.push(`LEFT JOIN ${alias} ON ${on(alias)}`);
    select.push(`(${alias}.${key[0]} IS NULL) AS ${t.table}_below_floor`);
    for (const m of t.metrics) select.push(`${alias}.${out(m.id)}`, `${alias}.${out(m.id)}_pctl`, `${alias}.${out(m.id)}_n`);
  });
  const sql = `WITH ${ctes.join(", ")} SELECT ${select.join(", ")} FROM k ${joins.join(" ")} ORDER BY k.slot`;
  return gate(sql, catalog);
}

function gate(sql: string, catalog: ScoutingCatalog): string {
  const check = checkSql(
    sql,
    catalog.tables.map((t) => t.table),
  );
  if (!check.ok) throw new Error(`scouting SQL rejected: ${check.reason}`);
  return sql;
}
