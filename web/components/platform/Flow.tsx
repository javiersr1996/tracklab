"use client";

import { useRef } from "react";
import { formatBytes } from "../../lib/format";
import { useCountUp } from "../../lib/motion";
import { counterKey, type PlatformLayer } from "../../lib/platform";

// The layers' counters (P20, task 174). Until P20 they played one layer after another in an 8 s
// loop that started over from 0, so most of the time most layers read 0 (four of six, 10 s after
// load), and the server sent them all at 0. Now every counter is the exact figure of
// `platform.json` in the server's HTML; the first time the figure comes into view all six count up
// together from 0 (`useCountUp`, the home's count) and land on it, once. `figure.platform`'s
// `data-state` is the count's phase (still, idle, counting, done), which the e2e read.

// One line per layer: what the code does, no figure (the counters are the figures). Each is
// backed by the code named beside it, so a change there is a change here.
const LAYER_BLURB: Partial<Record<PlatformLayer["layer"], string>> = {
  // ingest/manifest.py (commit and sha256 per file), ingest/fetch.py (plain HTTP, hashed while streaming)
  raw: "Pinned commit, sha256 per file, plain HTTP. A file already on disk with the right hash is verified, not downloaded again.",
  // bronze/common.py: typed schema, ZSTD, atomic write, sha256 in the Parquet metadata
  bronze: "One typed Parquet per match, ZSTD, written atomically, source sha256 in its metadata.",
  // dbt/models/silver/frames.sql: partition_by sport, native_match_id
  silver: "dbt on DuckDB: one schema for both sports, partitioned by sport and match.",
  // dbt/models/gold: dim_player, dim_season_team, dim_metric, fact_player_season_metric
  gold: "Dimensional model: player, team and metric dimensions and a long fact, plus wide aggregates.",
};

function formatCount(n: number): string {
  return n.toLocaleString("en-US");
}

function valueAt(final: number, t: number): number {
  return Math.round(final * t);
}

export function Flow({ layers }: { layers: PlatformLayer[] }) {
  const el = useRef<HTMLElement>(null);
  // From when the figure's top is a tenth of the window above its foot.
  const { phase, t } = useCountUp(el, 0, "0px 0px -10% 0px");

  return (
    <figure ref={el} className="platform" data-state={phase}>
      <div className="platform-layers">
        {layers.map((layer) => {
          const bytes = valueAt(layer.bytes, t);

          return (
            <div className="platform-layer" key={layer.layer} data-phase={phase === "counting" ? "active" : "finished"}>
              <h3>{layer.layer}</h3>
              {LAYER_BLURB[layer.layer] && <p className="platform-blurb">{LAYER_BLURB[layer.layer]}</p>}
              <div className="platform-bar">
                <div className="platform-bar-fill" style={{ width: `${Math.round(t * 100)}%` }} />
              </div>
              <dl className="platform-counters">
                <div>
                  <dt>files</dt>
                  <dd data-counter={counterKey(layer.layer, "files")}>
                    {formatCount(valueAt(layer.files, t))}
                  </dd>
                </div>
                {layer.rows !== null && (
                  <div>
                    <dt>rows</dt>
                    <dd data-counter={counterKey(layer.layer, "rows")}>
                      {formatCount(valueAt(layer.rows, t))}
                    </dd>
                  </div>
                )}
                <div>
                  <dt>bytes</dt>
                  <dd data-counter={counterKey(layer.layer, "bytes")}>{formatCount(bytes)}</dd>
                  <span className="platform-bytes-human">({formatBytes(bytes)})</span>
                </div>
                {layer.downloaded !== undefined && (
                  <div>
                    <dt>downloaded this run</dt>
                    <dd data-counter={counterKey(layer.layer, "downloaded")}>
                      {formatCount(valueAt(layer.downloaded, t))}
                    </dd>
                  </div>
                )}
                {layer.verified !== undefined && (
                  <div>
                    <dt>verified against sha256</dt>
                    <dd data-counter={counterKey(layer.layer, "verified")}>
                      {formatCount(valueAt(layer.verified, t))}
                    </dd>
                  </div>
                )}
                {layer.bytes_read !== undefined && (
                  <div>
                    <dt>bytes read, decompressed</dt>
                    <dd data-counter={counterKey(layer.layer, "bytes_read")}>
                      {formatCount(valueAt(layer.bytes_read, t))}
                    </dd>
                  </div>
                )}
                <div>
                  <dt>seconds (longest step)</dt>
                  <dd data-counter={counterKey(layer.layer, "seconds")}>
                    {(layer.seconds * t).toFixed(1)}
                  </dd>
                </div>
              </dl>
              {layer.note && (
                <details className="platform-note">
                  <summary>How it is counted</summary>
                  <p>{layer.note}</p>
                </details>
              )}
            </div>
          );
        })}
      </div>
    </figure>
  );
}
