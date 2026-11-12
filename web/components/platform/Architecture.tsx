import Link from "next/link";
import { formatBytes } from "../../lib/format";
import { type LayerName, PLATFORM, rawSourceMeta } from "../../lib/platform";
import { EUROLEAGUE } from "../../lib/sections";

// The architecture as one picture (P20, task 173), on the home page and at the head of
// /engineering: SkillCorner's sources, the layers Dagster runs, what the browser reads,
// and the two paths beside them (Postgres, EuroLeague). Real text in boxes on a CSS grid, so it
// restacks top to bottom on a phone instead of shrinking; the connectors are CSS, decorative.
// Every byte figure is platform.json's (`raw_sources[]`, `layers[]`), none is typed. Each layer's
// tool is what Flow.tsx's layer lines and the code behind them say; its role is a few words.
const STAGES: Record<LayerName, { role: string; tool: string; href?: string }> = {
  raw: { role: "the provider's files, verified", tool: "pinned commit + sha256", href: "/engineering#sources" },
  bronze: { role: "one typed table per match", tool: "typed Parquet, ZSTD" },
  silver: { role: "the conformed schema", tool: "dbt on DuckDB, one schema for both sports", href: "/engineering#silver-models" },
  gold: { role: "season aggregates", tool: "dimensional model", href: "/warehouse" },
  quality: { role: "one figure per match", tool: "checks", href: "/engineering/quality" },
  publish: { role: "what this site reads", tool: "JSON + Parquet" },
};

export function Architecture() {
  return (
    <figure className="arch" aria-labelledby="arch-caption" data-architecture>
      <div className="arch-grid">
        <div className="arch-box arch-flow arch-sources">
          <p className="arch-label">SkillCorner open data</p>
          <ul>
            {PLATFORM.raw_sources.map((s) => {
              const meta = rawSourceMeta(s.source_id);
              return (
                <li key={s.source_id} data-arch-source={s.source_id}>
                  {meta ? <a href={meta.href}>{meta.what}</a> : s.source_id}{" "}
                  <span className="arch-bytes">{formatBytes(s.bytes)}</span>
                </li>
              );
            })}
          </ul>
        </div>
        <p className="arch-dagster">
          <Link href="/engineering#lineage" prefetch={false}>
            Dagster
          </Link>{" "}
          <span>runs the layers as one asset graph</span>
        </p>
        <div className="arch-frame" aria-hidden="true" />
        <ol className="arch-stages">
          {PLATFORM.layers.map((l) => {
            const stage = STAGES[l.layer];
            return (
              <li key={l.layer} className="arch-box arch-flow arch-stage" data-arch-stage={l.layer}>
                <p className="arch-name">
                  {stage.href ? (
                    <Link href={stage.href} prefetch={false}>
                      {l.layer}
                    </Link>
                  ) : (
                    l.layer
                  )}
                </p>
                <p className="arch-bytes" data-layer-bytes={l.layer}>
                  {formatBytes(l.bytes)}
                </p>
                <p className="arch-tool">{stage.tool}</p>
                <p className="arch-role">{stage.role}</p>
              </li>
            );
          })}
        </ol>
        <div className="arch-box arch-consumers">
          <p className="arch-label">In your browser</p>
          <ul>
            <li>
              <Link href="/tracking/replay" prefetch={false}>
                Canvas replay
              </Link>
            </li>
            <li>
              <Link href="/warehouse" prefetch={false}>
                DuckDB-WASM
              </Link>{" "}
              <span>on Parquet by HTTP range</span>
            </li>
            <li>
              <Link href="/learn" prefetch={false}>
                Lessons
              </Link>
            </li>
          </ul>
        </div>
        <div className="arch-box arch-side arch-pg">
          <p className="arch-name">
            <Link href="/engineering#postgres" prefetch={false}>
              Postgres
            </Link>
          </p>
          <p className="arch-role">gold&apos;s second path, loaded by a command outside Dagster</p>
        </div>
        <div className="arch-side arch-el">
          <a href={EUROLEAGUE.href} className="arch-el-end">
            EuroLeague game feed
          </a>
          <span className="arch-el-line" aria-hidden="true" />
          <span className="arch-el-label">public API, pulled incrementally: aggregates only, not counted in the bytes</span>
          <span className="arch-el-line" aria-hidden="true" />
          <Link href="/euroleague" prefetch={false} className="arch-el-end">
            /euroleague
          </Link>
        </div>
      </div>
      <figcaption id="arch-caption">
        The pipeline in order: SkillCorner&apos;s open sources into raw, then bronze, silver, gold, quality and
        publish, the layers Dagster runs, each with the bytes the latest build measured; what publish
        writes is read in your browser. Gold also loads into Postgres, outside Dagster. EuroLeague is a lane of
        its own: only its aggregates are published, and its bytes are not counted.
      </figcaption>
    </figure>
  );
}
