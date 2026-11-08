"use client";

import type { PlayerKey } from "../../lib/scouting/sql";
import {
  type CatalogTable,
  formatPctl,
  formatValue,
  type Pool,
  pctlStep,
  sameKey,
  sampleNoun,
  SMALL_POOL,
  smallPoolNote,
  scaleText,
  type ScoutRow,
  type Sort,
  type SortColumn,
} from "../../lib/scouting/catalog";

// The table of /warehouse/scouting (task 136): one body per pool (a football position group, or
// the basketball league), its head saying who is in it, then the rows in the order picked. Each
// metric's cell is tinted by the percentile's fifth (the --pct-* steps) and prints the percentile
// or the value. Sorting and filtering happen on the result in this browser and never touch a
// percentile. Every value is text: React escapes it.

export type Slot = "a" | "b";

const DASH = "–";

export function ScoutTable({
  table,
  pools,
  rows,
  sort,
  onSort,
  show,
  a,
  b,
  onPick,
}: {
  table: CatalogTable;
  pools: Pool[];
  rows: ScoutRow[];
  sort: Sort;
  onSort: (column: SortColumn) => void;
  show: "pctl" | "value";
  a: PlayerKey;
  b: PlayerKey;
  onPick: (slot: Slot, key: PlayerKey) => void;
}) {
  const football = table.sport === "football";
  const lead = football ? 4 : 3;
  const sampleHead = sampleNoun(table, 2);

  const head = (column: SortColumn, label: string, sub?: string) => {
    const on = sort.column === column;
    return (
      <th
        scope="col"
        key={column}
        aria-sort={on ? (sort.descending ? "descending" : "ascending") : undefined}
        className={column === "name" ? "scout-player" : column === "team" ? "scout-team" : undefined}
      >
        <button type="button" className="scout-sort" data-sort={column} onClick={() => onSort(column)}>
          <span className="scout-sort-label">
            {label}
            <span className="scout-sort-mark" aria-hidden="true">
              {on ? (sort.descending ? " ↓" : " ↑") : ""}
            </span>
          </span>
          {sub ? <span className="scout-sort-sub">{sub}</span> : null}
        </button>
      </th>
    );
  };

  return (
    <div className="table-scroll scout-scroll">
      <table className="scout-table" data-table={table.table}>
        <thead>
          <tr>
            {head("name", "Player")}
            {head("team", "Team")}
            {football ? head("age", "Age") : null}
            {head("sample", sampleHead[0].toUpperCase() + sampleHead.slice(1))}
            {table.metrics.map((m, i) => head(`m:${i}`, m.label, scaleText(m)))}
          </tr>
        </thead>
        {pools.map((pool) => {
          const inPool = rows.filter((r) => r.group === pool.group);
          return (
            <tbody
              key={pool.group ?? "league"}
              data-pool={pool.group ?? "league"}
              data-pool-rows={pool.rows}
              data-pool-players={pool.players}
              data-pool-sample={pool.sample}
            >
              <tr className="scout-pool">
                <th scope="colgroup" colSpan={lead}>
                  <span className="scout-pool-text">
                    <strong>{pool.group ?? "The league"}</strong>: {pool.players} players,{" "}
                    {pool.sample.toLocaleString("en-US")} {sampleNoun(table, pool.sample)} between them
                    {pool.rows !== pool.players ? ` (${pool.rows} rows)` : ""}
                    {inPool.length !== pool.rows ? `; ${inPool.length} shown` : ""}
                    {pool.players < SMALL_POOL ? (
                      <>
                        {". "}
                        <span data-small-pool>{smallPoolNote(pool.players)}</span>
                      </>
                    ) : null}
                  </span>
                </th>
                {table.metrics.map((m, i) => (
                  <td key={m.id} data-pool-n={pool.n[i]}>
                    {pool.n[i] !== pool.rows ? `n ${pool.n[i]}` : null}
                  </td>
                ))}
              </tr>
              {inPool.map((r) => {
                const isA = sameKey(r.key, a);
                const isB = sameKey(r.key, b);
                return (
                  <tr
                    key={r.id}
                    data-key={r.id}
                    data-alias={r.aliasOf ?? undefined}
                    data-picked={isA ? "a" : isB ? "b" : undefined}
                  >
                    <th scope="row" className="scout-player">
                      <span className="scout-player-in">
                        <span className="scout-picks">
                          {(["a", "b"] as const).map((slot) => {
                            const on = slot === "a" ? isA : isB;
                            return (
                              <button
                                key={slot}
                                type="button"
                                className="scout-pick"
                                data-slot={slot}
                                aria-pressed={on}
                                aria-label={`Compare ${r.name} as ${slot.toUpperCase()}`}
                                onClick={() => onPick(slot, r.key)}
                              >
                                {slot.toUpperCase()}
                              </button>
                            );
                          })}
                        </span>
                        <span className="scout-name">
                          {r.name}
                          {r.aliasOf !== null ? <span className="scout-tag">old id</span> : null}
                          {r.hasAlias !== null ? <span className="scout-tag">new id</span> : null}
                        </span>
                      </span>
                    </th>
                    <td className="scout-team">{r.team}</td>
                    {football ? <td data-col="age">{r.age ?? DASH}</td> : null}
                    <td data-col="sample">{r.sample}</td>
                    {r.cells.map((c, i) => {
                      const m = table.metrics[i];
                      return (
                        <td
                          key={m.id}
                          className="scout-cell"
                          data-metric={m.id}
                          data-step={c.pctl === null ? undefined : pctlStep(c.pctl)}
                          data-pctl={c.pctl ?? undefined}
                          data-value={c.value ?? undefined}
                        >
                          {c.pctl === null || c.value === null
                            ? DASH
                            : show === "pctl"
                              ? formatPctl(c.pctl)
                              : formatValue(m, c.value)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          );
        })}
      </table>
    </div>
  );
}
