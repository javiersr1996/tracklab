import scoutingJson from "../../public/data/scouting.json";
import type { QueryResult } from "../duckdb/engine";
import type { RawValue } from "../warehouse/cell";
import type { PlayerKey, ScoutingCatalog, ScoutingMetric, ScoutingTable } from "./sql";

// What /warehouse/scouting (task 136) reads from `scouting.json` and from the engine's results,
// as plain functions: the catalog with its pools and probes, the state of the page's URL, the rows
// of a table query and the two players of a comparison. Every figure the page prints comes from
// here, out of the JSON or out of a result; none is typed.

export type Sport = "football" | "basketball";
export const SPORTS: readonly Sport[] = ["football", "basketball"];

export interface ScoutingPool {
  group: string | null;
  rows: number;
  players: number;
  sample_total: number;
  // Rows with a value for each metric, in the catalog's order.
  n: number[];
}

export interface ScoutingProbe extends PlayerKey {
  in_pool: boolean;
  // Per metric id: [value, percentile], or null where the probe has no value for the metric.
  values?: Record<string, [number, number] | null>;
}

export interface CatalogTable extends ScoutingTable {
  sport: Sport;
  file: string;
  pools: ScoutingPool[];
  probes: ScoutingProbe[];
}

export interface DefaultPlayer extends PlayerKey {
  player_name: string;
  team_name: string;
  age?: number;
}

export interface ScoutingFile extends ScoutingCatalog {
  schema_version: number;
  default_pairs: Record<Sport, [DefaultPlayer, DefaultPlayer]>;
  aliases: { player_id: number; canonical_player_id: number }[];
  tables: CatalogTable[];
}

// The metrics of a probe the head panel can draw: a metric the probe has no value for has no bar.
export function probeMetrics(t: ScoutingTable, probe: ScoutingProbe): { id: string; label: string; pctl: number }[] {
  return t.metrics.flatMap((m) => {
    const pctl = probe.values?.[m.id]?.[1];
    return pctl === undefined ? [] : [{ id: m.id, label: m.label, pctl }];
  });
}

export const SCOUTING = scoutingJson as unknown as ScoutingFile;

export const tablesOf = (sport: Sport) => SCOUTING.tables.filter((t) => t.sport === sport);
export const tableOf = (table: string) => SCOUTING.tables.find((t) => t.table === table);

// Names the page gives the tables and their sample columns: words, not figures.
export const TABLE_LABEL: Record<string, string> = {
  fb_physical: "Physical",
  fb_passing: "Passing",
  fb_obr: "Off-ball runs",
  bb_shots: "Shots",
  bb_drives: "Drives",
  bb_picks: "Picks",
};

const SAMPLE_NOUN: Record<string, [string, string]> = {
  count_match: ["match", "matches"],
  performance_count: ["performance", "performances"],
  games_played: ["game", "games"],
};

export function sampleNoun(t: ScoutingTable, count: number): string {
  const [one, many] = SAMPLE_NOUN[t.sample] ?? ["row", "rows"];
  return count === 1 ? one : many;
}

// The number in a floor such as `count_match >= 5`.
export const floorMin = (t: ScoutingTable) => Number(/>= (\d+)$/.exec(t.floor)?.[1]);

// The scale of a metric as its column head says it.
export function scaleText(m: ScoutingMetric): string {
  const unit = m.unit ? `, ${m.unit}` : "";
  switch (m.scale) {
    case "per_match":
      return `per match${unit}`;
    case "per_action":
      return `per action${unit}`;
    case "per_30_tip":
      return "per 30 min in possession";
    case "per_hundred":
      return "per hundred";
    case "per_one":
      return "per one";
    default:
      return m.unit;
  }
}

const DECIMALS: Record<string, number> = { per_one: 3, per_hundred: 1, m_per_min: 1, km_per_h: 2, per_30_tip: 2, per_action: 2 };

export function formatValue(m: ScoutingMetric, value: number): string {
  const d = m.scale === "per_match" ? (m.unit === "m" ? 0 : 2) : (DECIMALS[m.scale] ?? 2);
  return value.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

// The percentile as the SQL rounds it, one decimal.
export const formatPctl = (p: number) => p.toFixed(1);

// The cyan step of a percentile cell, by fifth: 0 (under 20) has no fill, 4 is 80 or more.
export const pctlStep = (p: number) => (p >= 80 ? 4 : p >= 60 ? 3 : p >= 40 ? 2 : p >= 20 ? 1 : 0);

// ---- The URL: ?sport&table&group&a&b ------------------------------------------------------------

// A player's whole key as the URL writes it: `player_id-team_id` in basketball, then
// `-position_group` in football (a player can have one row per team and per position).
export const keyText = (k: PlayerKey) =>
  [k.player_id, k.team_id, ...(k.position_group ? [k.position_group] : [])].join("-");

export const sameKey = (x: PlayerKey, y: PlayerKey) => keyText(x) === keyText(y);

const KEY = /^(\d{1,9})-(\d{1,9})(?:-([A-Za-z][A-Za-z ]{0,39}))?$/;

// The position groups of a sport's pools, from the JSON.
export const groupsOf = (sport: Sport) =>
  [...new Set(tablesOf(sport).flatMap((t) => t.pools.map((p) => p.group)))].filter((g): g is string => g !== null);

// A key read from the URL, or null when it is not one this sport can have: integers, and in
// football one of the JSON's position groups (basketball has none).
export function parseKey(text: string | null, sport: Sport): PlayerKey | null {
  const m = text === null ? null : KEY.exec(text);
  if (!m) return null;
  const key: PlayerKey = { player_id: Number(m[1]), team_id: Number(m[2]) };
  if (sport === "basketball") return m[3] === undefined ? key : null;
  return m[3] !== undefined && groupsOf(sport).includes(m[3]) ? { ...key, position_group: m[3] } : null;
}

export interface ScoutParams {
  sport: Sport;
  table: string;
  // A football position group, or null for all of them.
  group: string | null;
  a: PlayerKey;
  b: PlayerKey;
}

const keyOf = (p: PlayerKey): PlayerKey => ({
  player_id: p.player_id,
  team_id: p.team_id,
  ...(p.position_group ? { position_group: p.position_group } : {}),
});

export const defaultPair = (sport: Sport): [PlayerKey, PlayerKey] => [
  keyOf(SCOUTING.default_pairs[sport][0]),
  keyOf(SCOUTING.default_pairs[sport][1]),
];

// The page's state from its query string. Anything that is not in the JSON falls back: an
// unknown sport to football, a table of another sport to the sport's first, a group the table's
// pools do not have to all groups, a key that does not parse to the default pair's player.
export function readParams(query: URLSearchParams): ScoutParams {
  const sportText = query.get("sport");
  const sport: Sport = SPORTS.find((s) => s === sportText) ?? "football";
  const tables = tablesOf(sport);
  const table = tables.find((t) => t.table === query.get("table")) ?? tables[0];
  const groupText = query.get("group");
  const group = table.partition && table.pools.some((p) => p.group === groupText) ? groupText : null;
  const [a, b] = defaultPair(sport);
  return {
    sport,
    table: table.table,
    group,
    a: parseKey(query.get("a"), sport) ?? a,
    b: parseKey(query.get("b"), sport) ?? b,
  };
}

export function paramsQuery(p: ScoutParams): string {
  const q = new URLSearchParams({ sport: p.sport, table: p.table });
  if (p.group) q.set("group", p.group);
  q.set("a", keyText(p.a));
  q.set("b", keyText(p.b));
  return q.toString();
}

// ---- A table query's rows ----------------------------------------------------------------------

export interface Cell {
  value: number | null;
  pctl: number | null;
}

export interface ScoutRow {
  key: PlayerKey;
  id: string;
  name: string;
  team: string;
  group: string | null;
  sample: number;
  age: number | null;
  // The canonical id when this row's player id is one the provider replaced (an alias).
  aliasOf: number | null;
  // The alias id when this row's id replaced one that also has a row in the same team.
  hasAlias: number | null;
  cells: Cell[];
}

const num = (v: RawValue | undefined) => (typeof v === "number" ? v : null);
const text = (v: RawValue | undefined) => (v === null || v === undefined ? "" : String(v));

function reader(r: QueryResult) {
  const index = new Map(r.columns.map((c, i) => [c, i]));
  return (row: RawValue[], column: string) => {
    const i = index.get(column);
    return i === undefined ? undefined : row[i];
  };
}

// The rows of `tableSql` (lib/scouting/sql.ts): key, name, team, sample, age, `<id>`, `<id>_pctl`.
export function rowsOf(t: CatalogTable, r: QueryResult): ScoutRow[] {
  const get = reader(r);
  const canonical = new Map(SCOUTING.aliases.map((a) => [a.player_id, a.canonical_player_id]));
  const rows = r.values.map((row): ScoutRow => {
    const group = t.partition ? text(get(row, "position_group")) : null;
    const key: PlayerKey = { player_id: num(get(row, "player_id"))!, team_id: num(get(row, "team_id"))! };
    if (group !== null) key.position_group = group;
    return {
      key,
      id: keyText(key),
      name: text(get(row, "player_name")),
      team: text(get(row, "team_name")),
      group,
      sample: num(get(row, "sample")) ?? 0,
      age: num(get(row, "age")),
      aliasOf: canonical.get(key.player_id) ?? null,
      hasAlias: null,
      cells: t.metrics.map((m) => ({ value: num(get(row, m.id)), pctl: num(get(row, `${m.id}_pctl`)) })),
    };
  });
  for (const row of rows) {
    if (row.aliasOf === null) continue;
    const other = rows.find((o) => o.key.player_id === row.aliasOf && o.key.team_id === row.key.team_id);
    if (other) other.hasAlias = row.key.player_id;
  }
  return rows;
}

export interface Pool {
  group: string | null;
  rows: number;
  players: number;
  sample: number;
  // Rows with a value, per metric: a metric's pool leaves out the NULLs.
  n: number[];
}

// The pools of a loaded table, counted from its rows (the JSON holds the same figures, and the
// e2e compares the two).
export function poolsOf(t: CatalogTable, rows: ScoutRow[]): Pool[] {
  const groups = [...new Set(rows.map((r) => r.group))].sort((x, y) => (x ?? "").localeCompare(y ?? ""));
  return groups.map((group) => {
    const inGroup = rows.filter((r) => r.group === group);
    return {
      group,
      rows: inGroup.length,
      players: new Set(inGroup.map((r) => r.key.player_id)).size,
      sample: inGroup.reduce((sum, r) => sum + r.sample, 0),
      n: t.metrics.map((_, i) => inGroup.filter((r) => r.cells[i].value !== null).length),
    };
  });
}

// ---- Filters and order, in the browser on the result -----------------------------------------

// Lower case without accents, so "jose" finds "José".
const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export interface RowFilter {
  search: string;
  // Only players this old or younger at the JSON's date (football); null for all.
  maxAge: number | null;
}

// A filter picks rows; it never touches a percentile, which the pool fixed in the query.
export function filterRows(rows: ScoutRow[], f: RowFilter): ScoutRow[] {
  const q = fold(f.search.trim());
  return rows.filter(
    (r) =>
      (q === "" || fold(r.name).includes(q) || fold(r.team).includes(q)) &&
      (f.maxAge === null || (r.age !== null && r.age <= f.maxAge)),
  );
}

export type SortColumn = "name" | "team" | "age" | "sample" | `m:${number}`;
export interface Sort {
  column: SortColumn;
  descending: boolean;
}

function sortValue(r: ScoutRow, column: SortColumn): number | string | null {
  if (column === "name") return r.name;
  if (column === "team") return r.team;
  if (column === "age") return r.age;
  if (column === "sample") return r.sample;
  return r.cells[Number(column.slice(2))].value;
}

// By the raw value (not its text), a missing value last either way, then by name.
export function sortRows(rows: ScoutRow[], s: Sort): ScoutRow[] {
  const sign = s.descending ? -1 : 1;
  return [...rows].sort((x, y) => {
    const a = sortValue(x, s.column);
    const b = sortValue(y, s.column);
    if (a === null || b === null) return a === b ? x.name.localeCompare(y.name) : a === null ? 1 : -1;
    const order = typeof a === "string" ? a.localeCompare(String(b)) : a - Number(b);
    return order !== 0 ? sign * order : x.name.localeCompare(y.name);
  });
}

// ---- A comparison's two players ----------------------------------------------------------------

export interface ComparedTable {
  table: CatalogTable;
  // Under the table's sample floor (or with no row in it): no value, no percentile.
  below: boolean;
  pool: ScoutingPool | null;
  cells: Cell[];
  // Per metric, the rows of the player's pool with a value, counted by the comparison's query.
  n: (number | null)[];
}

export interface Compared {
  key: PlayerKey;
  // Null when the sport's first table has no row with this key (its name comes from there).
  name: string | null;
  team: string | null;
  age: number | null;
  tables: ComparedTable[];
}

// The two rows of `compareSql`, slot 0 then slot 1.
export function comparedOf(sport: Sport, r: QueryResult): Compared[] {
  const get = reader(r);
  return r.values.map((row) => {
    const key: PlayerKey = { player_id: num(get(row, "player_id"))!, team_id: num(get(row, "team_id"))! };
    const group = get(row, "position_group");
    if (typeof group === "string") key.position_group = group;
    const name = get(row, "player_name");
    return {
      key,
      name: typeof name === "string" ? name : null,
      team: typeof get(row, "team_name") === "string" ? text(get(row, "team_name")) : null,
      age: num(get(row, "age")),
      tables: tablesOf(sport).map((t) => {
        const below = get(row, `${t.table}_below_floor`) !== false;
        return {
          table: t,
          below,
          pool: t.pools.find((p) => p.group === (key.position_group ?? null)) ?? null,
          n: t.metrics.map((m) => (below ? null : num(get(row, `${t.table}__${m.id}_n`)))),
          cells: t.metrics.map((m) =>
            below
              ? { value: null, pctl: null }
              : { value: num(get(row, `${t.table}__${m.id}`)), pctl: num(get(row, `${t.table}__${m.id}_pctl`)) },
          ),
        };
      }),
    };
  });
}
