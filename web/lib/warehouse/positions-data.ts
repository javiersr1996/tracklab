// /warehouse/positions' data, read at build time (task 184a): every player row of `fb_physical` in
// the scouting page's pools (the rows that pass its sample floor, by position group), straight out
// of the published Parquet file through `node-engine.ts`. Nothing new is published: the page prints
// what a query of the console over the same file returns. Only the server imports this file.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { POSSESSIONS } from "../data";
import { decimalsOf, floorMin, formatValue, scaleText, tableOf } from "../scouting/catalog";
import { queryWarehouse } from "./node-engine";
import { axisOf, groupView, POSITION_METRIC_IDS, positionsSql, type PositionsView, roundAsDuckDb, SPOTS } from "./positions";

const PLAIN = /^[a-z][a-z0-9_]*$/;

export async function positionsView(): Promise<PositionsView> {
  const t = tableOf("fb_physical");
  if (!t || t.partition !== "position_group") throw new Error("scouting.json has no fb_physical table by position group");
  if (!/^[a-z][a-z0-9_]* >= \d{1,4}$/.test(t.floor)) throw new Error(`fb_physical's floor ${JSON.stringify(t.floor)}`);
  const metrics = POSITION_METRIC_IDS.map((id) => {
    const m = t.metrics.find((x) => x.id === id);
    if (!m || !PLAIN.test(m.expr)) throw new Error(`fb_physical has no plain column ${id}`);
    return m;
  });

  const rows = await queryWarehouse(`SELECT position_group, ${metrics.map((m) => m.expr).join(", ")} FROM fb_physical WHERE ${t.floor}`);
  const groups = [...new Set(rows.map((r) => String(r.position_group)))].sort();
  const unplaced = groups.filter((g) => !(g in SPOTS));
  if (unplaced.length) throw new Error(`no place on the pitch for ${unplaced.join(", ")}`);

  const about = await queryWarehouse("SELECT DISTINCT competition_name, season_name FROM fb_physical");
  if (about.length !== 1) throw new Error("fb_physical holds more than one competition and season");

  // The pitch of the first published football possession, as the home's card reads its court.
  const entry = POSSESSIONS.find((p) => p.sport === "football");
  if (!entry) throw new Error("index.json has no football possession");
  const { surface } = JSON.parse(readFileSync(join(process.cwd(), "public", "data", entry.file), "utf-8")) as {
    surface: { length_m: number; width_m: number };
  };

  return {
    floor: t.floor,
    floorMin: floorMin(t),
    competition: String(about[0].competition_name),
    season: String(about[0].season_name),
    pitch: { length: surface.length_m, width: surface.width_m },
    metrics: metrics.map((m) => {
      const values = (g: string) => rows.flatMap((r) => (r.position_group === g && typeof r[m.expr] === "number" ? [r[m.expr] as number] : []));
      const axis = axisOf(rows.flatMap((r) => (typeof r[m.expr] === "number" ? [r[m.expr] as number] : [])));
      return {
        id: m.id,
        label: m.label,
        unit: m.unit,
        scale: scaleText(m),
        domain: axis.domain,
        ticks: axis.ticks.map((v) => ({ value: v, text: v.toLocaleString("en-US", { minimumFractionDigits: axis.decimals, maximumFractionDigits: axis.decimals }) })),
        groups: groups.map((g) => groupView(g, values(g), (v) => formatValue(m, roundAsDuckDb(v, decimalsOf(m))))),
        sql: positionsSql(m.expr, t.floor, decimalsOf(m)),
      };
    }),
  };
}
