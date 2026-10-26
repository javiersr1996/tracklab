import type { ComponentType } from "react";
import type { SqlSlug } from "../../../lib/sql/course";
import { ExpressionsProse } from "./expressions";
import { GroupByProse } from "./group-by";
import { JoinsProse } from "./joins";
import { LongWideProse } from "./long-wide";
import { ScoutingProse } from "./scouting";
import { SelectProse } from "./select";
import { WhereProse } from "./where";
import { WindowsProse } from "./windows";

// The prose of each lesson of /sql, by slug: short sections before the worked example, in English,
// for an aspiring football or basketball analyst with no SQL. No number or name is typed in them:
// each comes from the lesson's facts through `<Fact>` (tests/sql-lessons.test.ts checks it).
export const PROSE: Record<SqlSlug, ComponentType> = {
  select: SelectProse,
  where: WhereProse,
  expressions: ExpressionsProse,
  "group-by": GroupByProse,
  joins: JoinsProse,
  "long-wide": LongWideProse,
  windows: WindowsProse,
  scouting: ScoutingProse,
};
