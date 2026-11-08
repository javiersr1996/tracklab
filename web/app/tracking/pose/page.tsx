"use client";

import { type ReactNode, useEffect, useState } from "react";
import { Pose } from "../../../components/pose/Pose";
import { Band, PageHead } from "../../../components/site/Band";
import type { PoseClip, PoseSummary } from "../../../lib/pose/types";

// `/tracking/pose` (tasks 56 and 63): the Body Pose of two matches in a viewer with its own projection,
// and what the project found. `pose.json` is fetched, then the clip on show, like the
// possessions the replay plays. Every figure is an element `data-fig="path"` whose text is
// `String(value at path)` in `pose.json`, or `data-clip-fig` for a path in the clip on show;
// the e2e reads the same files and compares. No figure is typed here.
const SUMMARY = "/data/pose.json";
const SAMPLE = "sample";

const at = (root: unknown, path: string): unknown =>
  path.split(".").reduce<unknown>((node, key) => (node as Record<string, unknown> | undefined)?.[key], root);

function S({ doc, p }: { doc: PoseSummary; p: string }) {
  return <span data-fig={p}>{String(at(doc, p))}</span>;
}

function C({ clip, p }: { clip: PoseClip; p: string }) {
  return <span data-clip-fig={p}>{String(at(clip, p))}</span>;
}

// A value with the sd propagated beside it; a value the metric could not say is a dash.
function Pm({ doc, row, v, sd }: { doc: PoseSummary; row: string; v: number; sd: number }) {
  const value = at(doc, `${row}.${v}`);
  if (value === null || value === undefined) return <>-</>;
  const spread = at(doc, `${row}.${sd}`);
  return (
    <>
      <span data-fig={`${row}.${v}`}>{String(value)}</span>
      {spread === null || spread === undefined ? null : (
        <>
          {" ± "}
          <span data-fig={`${row}.${sd}`}>{String(spread)}</span>
        </>
      )}
    </>
  );
}

// What the viewer does about each limit, by the limit's id in the clip.
const IN_THIS_VIEWER: Record<string, string> = {
  detected_only:
    "A player with no pose in a frame is drawn as the replay's disc where the clip lists him, and not at all where it does not. No skeleton is interpolated between frames or carried over from an earlier one.",
  z_relative:
    "Each body is drawn in its own frame, about the player's position; the pitch stays a flat map seen from above, with no floor and no vertical scale. Yaw and tilt turn the bodies, never the pitch.",
  separate_generation:
    "Positions are the pose file's own x and y, not the tracking's, and frames are matched by number, never by timestamp.",
};

// What each sub-criterion of `dies_at` (criteria.verdict_dies_at) says, in words.
const REASON: Record<string, string> = {
  m1: "too few players have enough windows with a cadence in the fast band",
  m2_coverage: "too few players have enough windows with a cadence in both bands",
  m2_sign: "too few players have a higher cadence in the fast band than in the slow one",
  m2_precision: "the median propagated sd is larger than the half spread between players frozen as the bar",
};

function Reason({ doc, p }: { doc: PoseSummary; p: string }) {
  const value = String(at(doc, p));
  return (
    <>
      <code data-fig={p}>{value}</code>: {REASON[value] ?? "a sub-criterion this page does not know"}
    </>
  );
}

function Status({ doc }: { doc: PoseSummary }) {
  const { status, dead_at: deadAt } = doc;
  let body: ReactNode;
  if (status === "alive") {
    body = (
      <>
        Alive. Match <S doc={doc} p="protocol.calibration" /> calibrated the instrument and match{" "}
        <S doc={doc} p="protocol.confirmation" /> confirmed it once (<code>M4</code>):{" "}
        <S doc={doc} p="verdict.confirmation.m4.m2_positive" /> of{" "}
        <S doc={doc} p="verdict.confirmation.m4.m2_players" /> players have a higher cadence in the fast
        band than in the slow one, and the median propagated sd is{" "}
        <S doc={doc} p="verdict.confirmation.m4.median_sd_hz" /> Hz, against the{" "}
        <S doc={doc} p="verdict.confirmation.m4.half_iqr_hz" /> Hz the protocol froze before match{" "}
        <S doc={doc} p="protocol.confirmation" /> was read.
      </>
    );
  } else if (status === "unreplicated") {
    body = (
      <>
        Not replicated by coverage; not dead. Match <S doc={doc} p="protocol.confirmation" /> has{" "}
        <S doc={doc} p="verdict.confirmation.coverage.players_ge_min_high" /> players with enough windows in
        the fast band and <S doc={doc} p="verdict.confirmation.coverage.players_ge_min_both" /> in both, where{" "}
        <code>M1</code> and <code>M2</code> ask for <S doc={doc} p="verdict.thresholds.min_players" />.
        <code> M4</code> cannot be judged, so what follows is published as it stands.
      </>
    );
  } else if (deadAt === "M4") {
    body = (
      <>
        Dead at <code>M4</code>, by <Reason doc={doc} p="verdict.confirmation.m4.dies_at" />. Match{" "}
        <S doc={doc} p="protocol.confirmation" /> did not replicate: the median propagated sd is <S doc={doc} p="verdict.confirmation.m4.median_sd_hz" /> Hz against the{" "}
        <S doc={doc} p="verdict.confirmation.m4.half_iqr_hz" /> Hz frozen, with{" "}
        <S doc={doc} p="verdict.confirmation.m4.m2_players" /> players in both bands.
      </>
    );
  } else if (deadAt === "M1") {
    body = (
      <>
        Dead at <code>M1</code>. Match <S doc={doc} p="protocol.calibration" /> has{" "}
        <S doc={doc} p="verdict.M1.players" /> players with enough windows, where{" "}
        <S doc={doc} p="verdict.M1.min_players" /> are needed. The confirmation match was never opened.
      </>
    );
  } else if (deadAt === "M2") {
    body = (
      <>
        Dead at <code>M2</code>, by <Reason doc={doc} p="verdict.dies_at" />. Match{" "}
        <S doc={doc} p="protocol.calibration" />:{" "}
        <S doc={doc} p="verdict.M2.positive" /> of <S doc={doc} p="verdict.M2.players_with_both" /> players
        have a higher cadence in the fast band, and the median propagated sd is{" "}
        <S doc={doc} p="verdict.M2.median_sd_hz" /> Hz against <S doc={doc} p="verdict.M2.half_iqr_hz" />{" "}
        Hz. The confirmation match was never opened.
      </>
    );
  } else {
    body = (
      <>
        Dead at the noise. The rule that chooses the window and the cap found no cell where the instrument
        is told from noise, so nothing after it was run and the confirmation match was never opened.
      </>
    );
  }
  return (
    <p data-section="status" data-status={status} data-dead-at={deadAt ?? ""}>
      {body}
    </p>
  );
}

function CoverageTable({ doc }: { doc: PoseSummary }) {
  const rows = Object.keys(doc.coverage).flatMap((match) =>
    Object.keys(doc.coverage[match].periods).map((period) => ({ match, period })),
  );
  return (
    <div className="table-scroll">
      <table data-table="coverage">
        <thead>
          <tr>
            <th>match</th>
            <th>period</th>
            <th>frames</th>
            <th>frames with a pose</th>
            <th>player-frames</th>
            <th>with a pose</th>
            <th>share of player-frames</th>
            <th>skeletons per frame, most</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ match, period }) => {
            const key = `${match}.${period}`;
            const base = `coverage.${match}.periods.${period}`;
            return (
              <tr key={key} data-row={key}>
                <td>{match}</td>
                <td>{period}</td>
                <td><S doc={doc} p={`${base}.frames`} /></td>
                <td><S doc={doc} p={`${base}.frames_with_pose`} /></td>
                <td><S doc={doc} p={`${base}.player_frames`} /></td>
                <td><S doc={doc} p={`${base}.with_pose`} /></td>
                <td><S doc={doc} p={`${base}.share_player_frames_with_pose`} /></td>
                <td><S doc={doc} p={`${base}.skeletons_per_frame.max`} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// Columns of a metric row, by name, so the table does not count them.
const col = (doc: PoseSummary, name: string) => doc.tables?.columns.indexOf(name) ?? -1;

function MetricTables({ doc }: { doc: PoseSummary }) {
  const tables = doc.tables;
  if (tables === null) return null;
  const [team, number, player, period, band, windows, finite] = [
    "team_id",
    "number",
    "player_id",
    "period",
    "band",
    "windows",
    "finite_s",
  ].map((name) => col(doc, name));
  return (
    <>
      {Object.keys(tables.matches).map((match) => (
        <div className="table-scroll" key={match}>
          <table data-table="players" data-match={match}>
            <caption>
              Match <S doc={doc} p={`protocol.${match === String(doc.protocol.calibration) ? "calibration" : "confirmation"}`} />, by team and
              shirt number, one row per player and band, the whole match
            </caption>
            <thead>
              <tr>
                <th>team</th>
                <th>no.</th>
                <th>player</th>
                <th>band</th>
                <th>windows</th>
                <th>finite in s</th>
                <th>cadence, Hz</th>
                <th>step, m</th>
                <th>ankle separation, m</th>
                <th>separation over step</th>
                <th>mean speed, m/s</th>
              </tr>
            </thead>
            <tbody>
              {tables.matches[match].map((row, i) => {
                if (row[period] !== "all") return null;
                const r = `tables.matches.${match}.${i}`;
                return (
                  <tr key={i} data-row={`${match}.${i}`}>
                    <td><S doc={doc} p={`${r}.${team}`} /></td>
                    <td><S doc={doc} p={`${r}.${number}`} /></td>
                    <td><S doc={doc} p={`${r}.${player}`} /></td>
                    <td>{String(row[band])}</td>
                    <td><S doc={doc} p={`${r}.${windows}`} /></td>
                    <td><S doc={doc} p={`${r}.${finite}`} /></td>
                    <td><Pm doc={doc} row={r} v={col(doc, "cad_s_p50_hz")} sd={col(doc, "cad_s_sd_hz")} /></td>
                    <td><Pm doc={doc} row={r} v={col(doc, "step_length_p50_m")} sd={col(doc, "step_length_sd_m")} /></td>
                    <td><Pm doc={doc} row={r} v={col(doc, "ankle_separation_p50_m")} sd={col(doc, "ankle_separation_sd_m")} /></td>
                    <td><Pm doc={doc} row={r} v={col(doc, "separation_over_step")} sd={col(doc, "separation_over_step_sd")} /></td>
                    <td><Pm doc={doc} row={r} v={col(doc, "speed_mean_m_s")} sd={-1} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}

// M3's concordance: the negative that sits beside the positive cadence, with no propagated error
// and saying so.
function Concordance({ doc }: { doc: PoseSummary }) {
  const tables = doc.tables;
  if (tables === null) return null;
  const [number, player, period, band, windows, finite] = [
    "number",
    "player_id",
    "period",
    "band",
    "windows",
    "finite_s",
  ].map((n) => col(doc, n));
  const diff = col(doc, "m3_abs_diff_p50_hz");
  const nan = col(doc, "m3_nan_h_share");
  return (
    <section data-section="m3">
      <h2>Where the second signal disagrees</h2>
      <p>
        <code>M3</code> compares the cadence of the ankles&apos; signal along the run with that of their
        vertical separation, in the fast band. It is a consistency check, not a verdict, and it carries no
        propagated error: <S doc={doc} p="tables.m3" />.
      </p>
      {Object.keys(tables.matches).map((match) => (
        <div className="table-scroll" key={match}>
          <table data-table="m3" data-match={match}>
            <caption>
              Match <S doc={doc} p={`protocol.${match === String(doc.protocol.calibration) ? "calibration" : "confirmation"}`} />{": the fast band, by team and shirt number"}
            </caption>
            <thead>
              <tr>
                <th>no.</th>
                <th>player</th>
                <th>windows</th>
                <th>finite in s</th>
                <th>median gap between the two cadences, Hz</th>
                <th>share of windows with no vertical cadence</th>
              </tr>
            </thead>
            <tbody>
              {tables.matches[match].map((row, i) => {
                if (row[period] !== "all" || row[band] !== "high" || row[diff] === null) return null;
                const r = `tables.matches.${match}.${i}`;
                return (
                  <tr key={i} data-row={`${match}.${i}`}>
                    <td><S doc={doc} p={`${r}.${number}`} /></td>
                    <td><S doc={doc} p={`${r}.${player}`} /></td>
                    <td><S doc={doc} p={`${r}.${windows}`} /></td>
                    <td><S doc={doc} p={`${r}.${finite}`} /></td>
                    <td><S doc={doc} p={`${r}.${diff}`} /></td>
                    <td><S doc={doc} p={`${r}.${nan}`} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
      <h3>What the protocol could not rule out</h3>
      <ul>
        {doc.protocol.blind_spots.map((_, i) => (
          <li key={i}>
            <S doc={doc} p={`protocol.blind_spots.${i}`} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function Protocol({ doc }: { doc: PoseSummary }) {
  return (
    <section data-section="protocol">
      <h2>The protocol, in the order it was written</h2>
      <p>
        Match <S doc={doc} p="protocol.calibration" /> calibrates and match{" "}
        <S doc={doc} p="protocol.confirmation" /> confirms.{" "}
        {doc.protocol.width === null ? (
          <>The window and the cap were never frozen: the rule that chooses them found no cell.</>
        ) : (
          <>
            The window is <S doc={doc} p="protocol.width" /> frames and the cap on the ankles&apos; predicted
            error is <S doc={doc} p="protocol.cap_cm" /> cm, both frozen before the confirmation match was
            read.
          </>
        )}{" "}
        The fast band starts at <S doc={doc} p="protocol.bands.high_m_s_from" /> m/s.
      </p>
      <ol className="pose-stages">
        {doc.protocol.stages.map((stage, i) => (
          <li key={stage.stage} data-stage={stage.stage}>
            <S doc={doc} p={`protocol.stages.${i}.stage`} />: <S doc={doc} p={`protocol.stages.${i}.what`} />,
            checksum <code data-fig={`protocol.stages.${i}.sha256`}>{stage.sha256}</code>
          </li>
        ))}
      </ol>
      <p data-scope>
        Scope: the matches above and no others; no rankings, no intent, no absolute height. The files are
        SkillCorner&apos;s open data and carry its limits, stated beside the viewer.
      </p>
    </section>
  );
}

function View({
  doc,
  clip,
  clipFile,
  failed,
  onClip,
}: {
  doc: PoseSummary;
  clip: PoseClip | null;
  clipFile: string;
  failed: boolean;
  onClip: (file: string) => void;
}) {
  const mae = "coverage.p90_mae_cm";
  return (
    <>
      <PageHead eyebrow="Body pose">
        <h1>{clip ? <><C clip={clip} p="joints.length" /> joints</> : "Body pose"}</h1>
        <Status doc={doc} />
      </PageHead>
      <Band dark>
        <div className="pose-layout">
          <div className="pose-stage">
            <div className="pose-clips">
              <label>
                Clip{" "}
                <select aria-label="Clip" value={clipFile} onChange={(e) => onClip(e.target.value)}>
                  <option value={SAMPLE}>the provider&apos;s sample</option>
                  {doc.clips.map((c) => (
                    <option key={c.file} value={c.file}>
                      {c.kind} of match {c.match_id}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {clip ? (
              <Pose key={clipFile} clip={clip} />
            ) : failed ? (
              <p role="alert">The clip could not be loaded.</p>
            ) : (
              <p role="status">Loading the clip.</p>
            )}
          </div>
          <aside className="pose-limits" data-section="limits">
            <h2>What the data does not say</h2>
            {doc.limits.map((limit, j) => (
              <div key={limit.id} data-limit={limit.id}>
                <blockquote data-fig={`limits.${j}.text`}>{limit.text}</blockquote>
                <p>
                  SkillCorner, <cite data-fig={`limits.${j}.readme`}>{limit.readme}</cite>.
                  {limit.id in IN_THIS_VIEWER ? ` In this viewer: ${IN_THIS_VIEWER[limit.id]}` : null}
                </p>
              </div>
            ))}
          </aside>
        </div>
      </Band>
      <Band>
        {clip ? (
          <>
            <section data-section="clip">
              <h2>The clip on show</h2>
              <p>
                Match <C clip={clip} p="match_id" />, period <C clip={clip} p="period" />, frames{" "}
                <C clip={clip} p="frame_lo" /> to <C clip={clip} p="frame_hi" /> at <C clip={clip} p="fps" /> fps.
                Cyan is the home team, magenta the away team. Bodies are drawn to the pitch&apos;s scale; follow a
                player to see one enlarged.{" "}
                {clip.selection ? (
                  <>
                    Chosen by rule: <span data-clip-fig="selection.rule">{clip.selection.rule}</span>.
                  </>
                ) : (
                  <>It is the provider&apos;s own sample of one phase.</>
                )}
              </p>
              <p>
                <C clip={clip} p="coverage.frames" /> frames and <C clip={clip} p="coverage.player_frames" />{" "}
                player-frames, of which <C clip={clip} p="coverage.with_joints" /> have a pose (a share of{" "}
                <C clip={clip} p="coverage.with_joints_share" />), from{" "}
                <C clip={clip} p="coverage.skeletons_per_frame.min" /> to{" "}
                <C clip={clip} p="coverage.skeletons_per_frame.max" /> skeletons per frame and{" "}
                <C clip={clip} p="coverage.joint_observations" /> joint observations.
              </p>
            </section>
            <section data-section="error">
              <h2>The predicted error travels with each joint</h2>
              <p>
                Every joint comes with SkillCorner&apos;s predicted error, <code>p90_mae_cm</code>. The viewer
                draws a joint and its bones solid up to the clip&apos;s median,{" "}
                <C clip={clip} p={`${mae}.median`} /> cm, fainter up to its <code>p90</code>,{" "}
                <C clip={clip} p={`${mae}.p90`} /> cm, and faintest beyond, up to{" "}
                <C clip={clip} p={`${mae}.max`} /> cm (the smallest is <C clip={clip} p={`${mae}.min`} /> cm).
              </p>
            </section>
          </>
        ) : null}
        <section data-section="coverage">
          <h2>How much of each match has a pose</h2>
          <p>
            Pose exists only where the provider resolved a player: in{" "}
            <S doc={doc} p={`coverage.${doc.protocol.calibration}.total.share_player_frames_with_pose`} /> of the
            player-frames of match <S doc={doc} p="protocol.calibration" /> and in{" "}
            <S doc={doc} p={`coverage.${doc.protocol.confirmation}.total.share_player_frames_with_pose`} /> of
            match <S doc={doc} p="protocol.confirmation" />.
          </p>
          <CoverageTable doc={doc} />
        </section>
        {doc.tables === null ? (
          <section data-section="no-tables">
            <h2>No table is published</h2>
            <p>A project that died is published without per-player tables.</p>
          </section>
        ) : (
          <section data-section="tables">
            <h2>Cadence and step, per match and per player</h2>
            <p>
              Each value is the median over that player&apos;s windows with a cadence, with the sd propagated
              from the joints&apos; predicted error beside it, and the number of windows it comes from in the
              same row. The windows of one player are not independent. <S doc={doc} p="tables.note" />.
            </p>
            <MetricTables doc={doc} />
          </section>
        )}
        <Concordance doc={doc} />
        <Protocol doc={doc} />
      </Band>
    </>
  );
}

export default function PosePage() {
  const [doc, setDoc] = useState<PoseSummary | "failed" | null>(null);
  const [file, setFile] = useState(SAMPLE);
  const [loaded, setLoaded] = useState<{ file: string; clip: PoseClip } | "failed" | null>(null);

  useEffect(() => {
    let live = true;
    fetch(SUMMARY)
      .then((r) => r.json() as Promise<PoseSummary>)
      .then((data) => live && setDoc(data))
      .catch(() => live && setDoc("failed"));
    return () => {
      live = false;
    };
  }, []);

  const url =
    typeof doc === "object" && doc !== null
      ? file === SAMPLE
        ? doc.phase406.file.replace(/^web\/public/, "")
        : `/data/${file}`
      : null;
  useEffect(() => {
    if (url === null) return;
    let live = true;
    fetch(url)
      .then((r) => r.json() as Promise<PoseClip>)
      .then((clip) => live && setLoaded({ file, clip }))
      .catch(() => live && setLoaded("failed"));
    return () => {
      live = false;
    };
  }, [url, file]);

  const clip = typeof loaded === "object" && loaded !== null && loaded.file === file ? loaded.clip : null;
  const ready = typeof doc === "object" && doc !== null;
  return (
    <main id="main" className="page pose" data-loaded={ready && clip !== null ? "true" : "false"}>
      {ready ? (
        <View doc={doc} clip={clip} clipFile={file} failed={loaded === "failed"} onClip={setFile} />
      ) : (
        <PageHead eyebrow="Body pose">
          <h1>Body pose</h1>
          {doc === "failed" || loaded === "failed" ? (
            <p role="alert">The pose data could not be loaded.</p>
          ) : null}
        </PageHead>
      )}
    </main>
  );
}
