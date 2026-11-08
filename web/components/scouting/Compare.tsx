"use client";

import {
  type Compared,
  floorMin,
  formatPctl,
  formatValue,
  keyText,
  sampleNoun,
  scaleText,
  SMALL_POOL,
  smallPoolNote,
  TABLE_LABEL,
} from "../../lib/scouting/catalog";

// The comparison of /warehouse/scouting (task 136): two players, A in cyan and B in magenta (a
// mark, never text), over every table of their sport, a pair of bars per metric with the
// percentile, the value and the metric's pool (`n`, the players of the pool with a value). Each
// percentile was computed inside that player's own pool, in its table, before the two rows were
// picked out (lib/scouting/sql.ts); under a table's sample floor a player has neither. A wide
// screen shows the sport's tables side by side; a narrow one only the table picked above (the
// others stay in the page, hidden by CSS), so the table of players is not three screens down.

export interface Who {
  name: string | null;
  team: string | null;
  age: number | null;
}

const SLOTS = ["a", "b"] as const;

function poolLine(t: Compared["tables"][number]): string {
  if (t.below) return `below the sample floor (under ${floorMin(t.table)} ${sampleNoun(t.table, 2)})`;
  if (!t.pool) return "no pool";
  return `${t.pool.group ?? "the league"}, ${t.pool.players} players, ${t.pool.sample_total.toLocaleString("en-US")} ${sampleNoun(
    t.table,
    t.pool.sample_total,
  )} between them`;
}

export function Compare({ players, who, current }: { players: Compared[]; who: Who[]; current: string }) {
  const [a, b] = players;
  return (
    <section className="scout-compare" aria-labelledby="scout-compare-h" data-compare-a={keyText(a.key)} data-compare-b={keyText(b.key)}>
      <h3 id="scout-compare-h">A beside B</h3>
      <div className="scout-versus">
        {players.map((p, i) => (
          <p key={SLOTS[i]} className="scout-who" data-slot={SLOTS[i]} data-found={who[i].name !== null}>
            <span className="scout-slot">{SLOTS[i].toUpperCase()}</span>
            <span className="scout-who-name">{who[i].name ?? `No row with the key ${keyText(p.key)}`}</span>
            <span className="scout-who-meta">
              {[who[i].team, p.key.position_group, who[i].age === null ? null : `${who[i].age} years old`]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </p>
        ))}
      </div>
      <p className="scout-compare-narrow">
        Here the comparison follows the table picked above; a wider screen shows every table of the sport side by
        side.
      </p>
      <div className="scout-compare-tables">
        {a.tables.map((ta, ti) => {
          const tb = b.tables[ti];
          const t = ta.table;
          const samePool = !ta.below && !tb.below && ta.pool === tb.pool;
          return (
            <section
              key={t.table}
              className="scout-compare-table"
              data-table={t.table}
              data-current={t.table === current || undefined}
            >
              <h4>{TABLE_LABEL[t.table] ?? t.table}</h4>
              <p className="scout-pools">
                {samePool ? (
                  <>Both in one pool: {poolLine(ta)}.</>
                ) : (
                  <>
                    A: {poolLine(ta)}. B: {poolLine(tb)}.
                  </>
                )}
              </p>
              {[ta, tb].some((x) => !x.below && x.pool && x.pool.players < SMALL_POOL) ? (
                <p className="scout-pools" data-small-pool>
                  {smallPoolNote(Math.min(...[ta, tb].flatMap((x) => (!x.below && x.pool ? [x.pool.players] : []))))}
                </p>
              ) : null}
              <ul className="scout-metrics">
                {t.metrics.map((m, i) => (
                  <li key={m.id} data-metric={m.id}>
                    <p className="scout-metric-head">
                      <span className="scout-metric-label">{m.label}</span>{" "}
                      <span className="scout-metric-scale">{scaleText(m)}</span>
                    </p>
                    {[ta, tb].map((side, s) => {
                      const c = side.cells[i];
                      const n = side.n[i];
                      return (
                        <div
                          key={SLOTS[s]}
                          className="scout-bar"
                          data-slot={SLOTS[s]}
                          data-below={side.below || undefined}
                          data-pctl={c.pctl ?? undefined}
                          data-value={c.value ?? undefined}
                          data-n={side.below ? undefined : n}
                        >
                          <span className="scout-slot" aria-label={SLOTS[s].toUpperCase()}>
                            {SLOTS[s].toUpperCase()}
                          </span>
                          {side.below ? (
                            <span className="scout-bar-note">below the sample floor</span>
                          ) : c.pctl === null || c.value === null ? (
                            <span className="scout-bar-note">no value</span>
                          ) : (
                            <>
                              <span className="scout-track" aria-hidden="true">
                                <span className="scout-fill" style={{ width: `${c.pctl}%` }} />
                              </span>
                              <span className="scout-bar-pct">{formatPctl(c.pctl)}</span>
                              <span className="scout-bar-value">{formatValue(m, c.value)}</span>
                              <span className="scout-bar-n">n {n}</span>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </section>
  );
}
