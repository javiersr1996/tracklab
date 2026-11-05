"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { formatBytes } from "../../lib/format";
import {
  comparedOf,
  defaultPair,
  filterRows,
  groupsOf,
  keyText,
  paramsQuery,
  poolsOf,
  readParams,
  rowsOf,
  SCOUTING,
  type ScoutParams,
  type Sort,
  type SortColumn,
  type Sport,
  SPORTS,
  sameKey,
  sortRows,
  TABLE_LABEL,
  tableOf,
  tablesOf,
} from "../../lib/scouting/catalog";
import { dispose, type QueryResult, run, snapshot, useScoutingEngine } from "../../lib/scouting/engine";
import { compareSql, type PlayerKey, tableSql } from "../../lib/scouting/sql";
import { Compare, type Who } from "./Compare";
import { ScoutTable, type Slot } from "./ScoutTable";

// The explorer of /warehouse/scouting (task 136). Its state is the URL's query
// (`?sport&table&group&a&b`): read in the client (`useSearchParams`, so the server sends the
// defaults inside a Suspense fallback) and written with `history.replaceState`, which Next keeps
// in step with `useSearchParams`. What the URL says is checked against `scouting.json`
// (`readParams`) and never reaches the SQL as text: the queries are built from the catalog, with
// integer ids and a position group the catalog lists (lib/scouting/sql.ts).
//
// Nothing of the engine is fetched until "Load the table": then the table's query runs, and the
// comparison of A and B (the JSON's default pair unless the URL names two players). After that,
// a new table or a new pair runs its query at once; each result is kept, so going back costs
// nothing. Search, U23 and the order work on the result in this browser and never change a
// percentile. `div.scout` carries what the e2e read: the engine's state, the URL's state, the
// loaded tables and the comparison's pair.

const U23 = 23;

export function Scouting() {
  return (
    <Suspense fallback={<Explorer query="" />}>
      <FromUrl />
    </Suspense>
  );
}

function FromUrl() {
  return <Explorer query={useSearchParams().toString()} />;
}

const compareId = (sport: Sport, pair: readonly [PlayerKey, PlayerKey]) => `compare:${sport}:${pair.map(keyText).join("|")}`;

function bytesLine(r: QueryResult): string {
  if (r.requests === 0) {
    return "fetched nothing from the network: the engine already held every byte it needed from an earlier query of this visit.";
  }
  return `${formatBytes(r.distinctBytes)} of Parquet fetched (${formatBytes(r.bytes)} requested) in ${r.requests.toLocaleString("en-US")} requests, ${r.rowCount.toLocaleString("en-US")} ${r.rowCount === 1 ? "row" : "rows"} in ${Math.round(r.ms)} ms.`;
}

function Explorer({ query }: { query: string }) {
  const s = useScoutingEngine();
  const p = readParams(new URLSearchParams(query));
  const [tables, setTables] = useState<Record<string, QueryResult>>({});
  const [compares, setCompares] = useState<Record<string, QueryResult>>({});
  const [started, setStarted] = useState(false);
  const [search, setSearch] = useState("");
  const [u23, setU23] = useState(false);
  const [sort, setSort] = useState<Sort>({ column: "name", descending: false });
  const [show, setShow] = useState<"pctl" | "value">("pctl");
  // One query at a time, in the order asked: the engine runs one and drops a second call.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const asked = useRef(new Set<string>());
  // The worker lives as long as the page that started it.
  useEffect(() => () => dispose(), []);

  function ask(id: string, sql: string, keep: (r: QueryResult) => void) {
    if (asked.current.has(id)) return;
    asked.current.add(id);
    queue.current = queue.current.then(async () => {
      await run(sql);
      const now = snapshot();
      if (now.query === "done" && now.result?.sql === sql) keep(now.result);
      else asked.current.delete(id); // failed: "Load the table" asks again
    });
  }

  function load(next: ScoutParams) {
    setStarted(true);
    ask(`table:${next.table}`, tableSql(SCOUTING, next.table), (r) => setTables((t) => ({ ...t, [next.table]: r })));
    const pair = [next.a, next.b] as const;
    const id = compareId(next.sport, pair);
    ask(id, compareSql(SCOUTING, next.sport, pair), (r) => setCompares((c) => ({ ...c, [id]: r })));
  }

  function go(next: ScoutParams) {
    window.history.replaceState(null, "", `?${paramsQuery(next)}`);
    if (started) load(next);
  }

  function chooseSport(sport: Sport) {
    if (sport === p.sport) return;
    const [a, b] = defaultPair(sport);
    setSort({ column: "name", descending: false });
    go({ sport, table: tablesOf(sport)[0].table, group: null, a, b });
  }

  function chooseTable(table: string) {
    if (table === p.table) return;
    const t = tableOf(table)!;
    setSort({ column: "name", descending: false });
    go({ ...p, table, group: t.pools.some((x) => x.group === p.group) ? p.group : null });
  }

  function pick(slot: Slot, key: PlayerKey) {
    const other = slot === "a" ? p.b : p.a;
    const current = slot === "a" ? p.a : p.b;
    if (sameKey(key, current)) return;
    // Picking the other slot's player swaps the two.
    const swap = sameKey(key, other);
    go(slot === "a" ? { ...p, a: key, b: swap ? p.a : p.b } : { ...p, b: key, a: swap ? p.b : p.a });
  }

  function sortBy(column: SortColumn) {
    const text = column === "name" || column === "team";
    setSort((old) => (old.column === column ? { column, descending: !old.descending } : { column, descending: !text }));
  }

  const t = tableOf(p.table)!;
  const football = p.sport === "football";
  const result = tables[p.table] ?? null;
  const rows = result ? rowsOf(t, result) : [];
  const pools = poolsOf(t, rows).filter((x) => p.group === null || x.group === p.group);
  const shown = sortRows(
    filterRows(
      rows.filter((r) => p.group === null || r.group === p.group),
      { search, maxAge: football && u23 ? U23 : null },
    ),
    sort,
  );
  const inView = rows.filter((r) => p.group === null || r.group === p.group).length;

  const cmp = compares[compareId(p.sport, [p.a, p.b])] ?? null;
  const players = cmp ? comparedOf(p.sport, cmp) : null;
  // A name the comparison's first table lacks (a goalkeeper has no physical row) comes from any
  // loaded table of the sport that has the key.
  const who: Who[] | null =
    players?.map((c) => {
      if (c.name !== null) return { name: c.name, team: c.team, age: c.age };
      for (const tt of tablesOf(p.sport)) {
        const r = tables[tt.table] ? rowsOf(tt, tables[tt.table]).find((x) => sameKey(x.key, c.key)) : undefined;
        if (r) return { name: r.name, team: r.team, age: r.age };
      }
      return { name: null, team: null, age: null };
    }) ?? null;

  const running = s.engine === "loading" || s.query === "running";
  const groups = football ? t.pools.map((x) => x.group).filter((g): g is string => g !== null) : [];
  const needsLoad = !result && !running;

  return (
    <div
      className="scout"
      data-engine={s.engine}
      data-query={s.query}
      data-run={s.runs}
      data-bytes-engine={s.engineBytes ?? undefined}
      data-sport={p.sport}
      data-table={p.table}
      data-group={p.group ?? ""}
      data-a={keyText(p.a)}
      data-b={keyText(p.b)}
      data-loaded={Object.keys(tables).sort().join(" ")}
      data-compared={players ? keyText(players[0].key) + " " + keyText(players[1].key) : ""}
      data-error={s.error ?? undefined}
    >
      <div className="scout-controls">
        <div className="scout-field">
          <span className="scout-field-label" id="scout-sport">
            Sport
          </span>
          <div className="scout-segments" role="group" aria-labelledby="scout-sport">
            {SPORTS.map((sport) => (
              <button
                key={sport}
                type="button"
                data-sport-button={sport}
                aria-pressed={sport === p.sport}
                className={sport === p.sport ? "primary" : undefined}
                onClick={() => chooseSport(sport)}
              >
                {sport}
              </button>
            ))}
          </div>
        </div>
        <div className="scout-field">
          <span className="scout-field-label" id="scout-table">
            Table
          </span>
          <div className="scout-segments" role="group" aria-labelledby="scout-table">
            {tablesOf(p.sport).map((x) => (
              <button
                key={x.table}
                type="button"
                data-table-button={x.table}
                aria-pressed={x.table === p.table}
                className={x.table === p.table ? "primary" : undefined}
                onClick={() => chooseTable(x.table)}
              >
                {TABLE_LABEL[x.table] ?? x.table}
              </button>
            ))}
          </div>
        </div>
        {football ? (
          <div className="scout-field">
            <label className="scout-field-label" htmlFor="scout-group">
              Position group
            </label>
            <select
              id="scout-group"
              value={p.group ?? ""}
              onChange={(e) => go({ ...p, group: groupsOf("football").includes(e.target.value) ? e.target.value : null })}
            >
              <option value="">All {groups.length} groups</option>
              {groups.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <div className="scout-field scout-search">
          <label className="scout-field-label" htmlFor="scout-search">
            Name or team
          </label>
          <input
            id="scout-search"
            type="search"
            autoComplete="off"
            spellCheck={false}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {football ? (
          <label className="scout-check">
            <input type="checkbox" checked={u23} onChange={(e) => setU23(e.target.checked)} />
            {U23} or under at {SCOUTING.age_reference}
          </label>
        ) : null}
        <div className="scout-field">
          <span className="scout-field-label" id="scout-show">
            Cells show
          </span>
          <div className="scout-segments" role="group" aria-labelledby="scout-show">
            {(["pctl", "value"] as const).map((v) => (
              <button
                key={v}
                type="button"
                data-show-button={v}
                aria-pressed={show === v}
                className={show === v ? "primary" : undefined}
                onClick={() => setShow(v)}
              >
                {v === "pctl" ? "Percentile" : "Value"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {needsLoad ? (
        <div className="scout-load">
          <button type="button" className="primary scout-load-button" onClick={() => load(p)}>
            Load the table
          </button>
          <p>
            Starts DuckDB in this browser, then reads {TABLE_LABEL[p.table]} and the comparison of A and B from the
            warehouse&apos;s Parquet files. Nothing of the engine is downloaded before you press it.
          </p>
        </div>
      ) : null}

      <div className="scout-status" role="status">
        {s.engine === "loading"
          ? "Starting DuckDB in this browser."
          : s.query === "running"
            ? "Running the query."
            : null}
      </div>
      {s.error ? <p role="alert">{s.error}</p> : null}

      {players && who ? <Compare players={players} who={who} current={p.table} /> : null}

      {result ? (
        <>
          <h3 className="scout-table-h">
            {TABLE_LABEL[t.table]}, {p.group ?? (football ? "every position group" : "the league")}
          </h3>
          <p className="scout-count" data-shown={shown.length} data-in-view={inView} data-under-floor={t.rows_total - rows.length}>
            {shown.length === inView
              ? `${inView} rows.`
              : `${shown.length} of ${inView} rows match the search${football && u23 ? " and the age" : ""}.`}{" "}
            {t.rows_total} rows in the table&apos;s Parquet file: {rows.length} pass the sample floor and are listed,{" "}
            {t.rows_total - rows.length} fall under it and are not. Pick A and B on any row to compare them; sort by any column. The table scrolls sideways.
          </p>
          <ScoutTable
            table={t}
            pools={pools}
            rows={shown}
            sort={sort}
            onSort={sortBy}
            show={show}
            a={p.a}
            b={p.b}
            onPick={pick}
          />
        </>
      ) : null}

      {started ? (
        <div className="scout-bytes" data-bytes>
          <p>
            <span className="scout-bytes-label">Engine</span>{" "}
            {s.engineBytes === null
              ? "not loaded yet."
              : `${formatBytes(s.engineBytes)} (the worker, the WebAssembly and the Parquet extension, at their encoded size), fetched when it started, from the network or from this browser's cache.`}
            {s.versions ? ` duckdb-wasm ${s.versions.package}, DuckDB ${s.versions.duckdb}.` : ""}
          </p>
          {result ? (
            <p data-bytes-table={result.distinctBytes}>
              <span className="scout-bytes-label">{TABLE_LABEL[t.table]}</span> {bytesLine(result)}
            </p>
          ) : null}
          {cmp ? (
            <p data-bytes-compare={cmp.distinctBytes}>
              <span className="scout-bytes-label">A beside B</span> (every table of the sport) {bytesLine(cmp)}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
