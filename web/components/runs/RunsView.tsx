import type { ReactNode } from "react";
import { at, type Runs, STAGES, type Stage } from "../../lib/runs/types";
import { Band, PageHead } from "../site/Band";
import { RunsHook } from "./Hook";

// `/tracking/runs` (task 53): P5 published with the outcome it had. Every figure is an element
// `data-fig="path"` whose text is `String(at(runs, path))`: the e2e reads the same path in the
// file the page was given and compares. Prose carries no figure of its own.

function F({ runs, p }: { runs: Runs; p: string }) {
  return <span data-fig={p}>{String(at(runs, p))}</span>;
}

function Td({ runs, p }: { runs: Runs; p: string }) {
  return <td data-fig={p}>{String(at(runs, p))}</td>;
}

// The label `line_testability` gives a subtype the line can test (pipeline/src/tracklab/runs/candidates.py).
const TESTABLE_ON_LINE = "testable on the line";

const yes = (flag: boolean) => (flag ? "yes" : "no");

function Scroll({ children }: { children: ReactNode }) {
  return (
    <div className="table-scroll">
      <table>{children}</table>
    </div>
  );
}

function StageFigures({ runs, stage }: { runs: Runs; stage: Stage }) {
  const base = `stages.${stage}.figures`;
  const figures = runs.stages[stage].figures;
  if (stage === "M1" && "probable_subtypes" in figures) {
    return (
      <>
        probable subtypes <F runs={runs} p={`${base}.probable_subtypes`} /> by the marker,{" "}
        <F runs={runs} p={`${base}.probable_by_line`} /> by the line,{" "}
        <F runs={runs} p={`${base}.probable_by_both`} /> by both (at least{" "}
        <F runs={runs} p={`${base}.needs_at_least`} /> needed on the marker)
      </>
    );
  }
  if (stage === "M2" && "instrument" in figures) {
    const i = `${base}.instrument`;
    return (
      <>
        all runs together: mean <F runs={runs} p={`${i}.mean_m`} /> m over{" "}
        <F runs={runs} p={`${i}.pairs`} /> pairs, same sign in{" "}
        <F runs={runs} p={`${i}.same_sign_matches`} /> of <F runs={runs} p={`${i}.of_matches`} />{" "}
        matches, p = <F runs={runs} p={`${i}.p`} />
      </>
    );
  }
  if ((stage === "M3" || stage === "M4") && Array.isArray(figures.subtypes)) {
    const key = stage === "M3" ? "pre_trend_ratio" : "detected_ratio";
    const what = stage === "M3" ? "pre-trend ratio" : "detected ratio";
    return (
      <ul>
        {(figures.subtypes as { subtype: string; leaves: boolean }[]).map((s, j) => (
          <li key={s.subtype} data-subtype={s.subtype} data-leaves={String(s.leaves)}>
            {s.subtype}: {what} <F runs={runs} p={`${base}.subtypes.${j}.${key}`} />,{" "}
            {s.leaves ? "leaves" : "stays"}
          </li>
        ))}
      </ul>
    );
  }
  const scalars = Object.keys(figures).filter((k) => typeof figures[k] !== "object");
  if (scalars.length === 0) return <>no figures published</>;
  return (
    <>
      {scalars.map((k, j) => (
        <span key={k}>
          {j > 0 ? ", " : ""}
          {k.replaceAll("_", " ")} <F runs={runs} p={`${base}.${k}`} />
        </span>
      ))}
    </>
  );
}

function Status({ runs }: { runs: Runs }) {
  const diedAt = runs.status === "dead" ? runs.dead_at : null;
  return (
    <p data-status={runs.status} data-dead-at={runs.dead_at ?? ""} className="runs-status">
      {diedAt ? (
        <>
          Dead at{" "}
          <strong>
            <F runs={runs} p="dead_at" />
          </strong>
          : <StageFigures runs={runs} stage={diedAt} />. The negative is published under the same
          title.{" "}
        </>
      ) : (
        <>
          Alive: <StageFigures runs={runs} stage="M5a" />.{" "}
        </>
      )}
      {runs.never_opened.opened ? (
        <>The held-out half was opened.</>
      ) : (
        <>
          The held-out half (<F runs={runs} p="never_opened.match_ids.length" /> matches) was never
          opened.
        </>
      )}
    </p>
  );
}

function Stages({ runs }: { runs: Runs }) {
  return (
    <section data-section="stages">
      <h2>Where it died</h2>
      <Scroll>
        <thead>
          <tr>
            <th scope="col">stage</th>
            <th scope="col">state</th>
            <th scope="col">the protocol&apos;s rule</th>
            <th scope="col">figures</th>
          </tr>
        </thead>
        <tbody>
          {STAGES.map((stage) => (
            <tr
              key={stage}
              data-stage={stage}
              data-state={runs.stages[stage].state}
              data-died={String(runs.status === "dead" && runs.dead_at === stage)}
            >
              <td className="text">{stage}</td>
              <td className="text" data-fig={`stages.${stage}.state`}>
                {runs.stages[stage].state}
              </td>
              <td className="text" data-fig={`stages.${stage}.rule`}>
                {runs.stages[stage].rule}
              </td>
              <td className="text">
                <StageFigures runs={runs} stage={stage} />
              </td>
            </tr>
          ))}
        </tbody>
      </Scroll>
    </section>
  );
}

function Negative({ runs }: { runs: Runs }) {
  const i = "instrument.marker.pooled";
  return (
    <section data-section="negative">
      <h2>What passed, next to what ruled it out</h2>
      <p>
        Marker: the displacement of the nearest opponent along the run, run minus placebo. Line:
        the defensive line, secondary, with the label its testability earned. Each subtype is read
        against the pre-trend (M3) and with the marker detected throughout (M4).
      </p>
      <Scroll>
        <thead>
          <tr>
            <th scope="col">subtype</th>
            <th scope="col">marker mean (m)</th>
            <th scope="col">matches, same sign</th>
            <th scope="col">of</th>
            <th scope="col">p</th>
            <th scope="col">passed the bar</th>
            <th scope="col">line label</th>
            <th scope="col">line mean (m)</th>
            <th scope="col">line passed the bar (secondary)</th>
            <th scope="col">M3 pre-trend ratio (marker)</th>
            <th scope="col">M3 (marker)</th>
            <th scope="col">M4 detected ratio (marker)</th>
            <th scope="col">M4 (marker)</th>
            <th scope="col">candidate</th>
          </tr>
        </thead>
        <tbody>
          <tr data-row="instrument">
            <td className="text">all runs (M2, the instrument)</td>
            <Td runs={runs} p={`${i}.mean_m`} />
            <Td runs={runs} p={`${i}.same_sign_matches`} />
            <Td runs={runs} p={`${i}.of_matches`} />
            <Td runs={runs} p={`${i}.p`} />
            <td>{yes(runs.instrument.marker.pooled.passes_bar)}</td>
            <td colSpan={8} className="text">
              M2 state: <F runs={runs} p="stages.M2.state" />
            </td>
          </tr>
          {runs.effect_by_subtype.map((s, j) => {
            const b = `effect_by_subtype.${j}`;
            return (
              <tr key={s.subtype} data-row="subtype" data-subtype={s.subtype}>
                <td className="text">{s.subtype}</td>
                <Td runs={runs} p={`${b}.marker.pooled.mean_m`} />
                <Td runs={runs} p={`${b}.marker.pooled.same_sign_matches`} />
                <Td runs={runs} p={`${b}.marker.pooled.of_matches`} />
                <Td runs={runs} p={`${b}.marker.pooled.p`} />
                <td>{yes(s.marker.pooled.passes_bar)}</td>
                <td className="text" data-fig={`${b}.line.testability`}>
                  {s.line.testability}
                </td>
                <Td runs={runs} p={`${b}.line.pooled.mean_m`} />
                <td data-cell="line-passes">
                  {s.line.testability === TESTABLE_ON_LINE
                    ? yes(s.line.pooled.passes_bar)
                    : "not testable"}
                </td>
                <Td runs={runs} p={`${b}.verdict.M3.pre_trend_ratio`} />
                <td>{s.verdict.M3.leaves ? "leaves" : "stays"}</td>
                <Td runs={runs} p={`${b}.verdict.M4.detected_ratio`} />
                <td>{s.verdict.M4.leaves ? "leaves" : "stays"}</td>
                <td>{yes(s.verdict.candidate)}</td>
              </tr>
            );
          })}
        </tbody>
      </Scroll>
      <p data-note="line-not-candidate">
        The line is the protocol&apos;s secondary quantity, run minus placebo. Its rule:{" "}
        <F runs={runs} p="protocol.quantities.secondary_rule" />. M3 and M4 were computed on the
        marker only.
      </p>
    </section>
  );
}

interface Group {
  label: string;
  path: string; // dotted path of a per_match array
  fields: { key: string; label: ReactNode }[];
}

// One row per match, one column group per source: the table that backs a pooled figure.
function PerMatch({
  runs,
  id,
  caption,
  groups,
}: {
  runs: Runs;
  id: string;
  caption: string;
  groups: Group[];
}) {
  const rows = at(runs, groups[0].path) as { match_id: number }[];
  return (
    <>
      <h3>{caption}</h3>
      <Scroll>
        <thead>
          <tr>
            <th scope="col">match</th>
            {groups.flatMap((g) =>
              g.fields.map((f) => (
                <th scope="col" key={`${g.label}.${f.key}`}>
                  {g.label} {f.label}
                </th>
              )),
            )}
          </tr>
        </thead>
        <tbody data-table={id}>
          {rows.map((row, j) => (
            <tr key={row.match_id} data-match={row.match_id}>
              <Td runs={runs} p={`${groups[0].path}.${j}.match_id`} />
              {groups.flatMap((g) =>
                g.fields.map((f) => (
                  <Td runs={runs} p={`${g.path}.${j}.${f.key}`} key={`${g.label}.${f.key}`} />
                )),
              )}
            </tr>
          ))}
        </tbody>
      </Scroll>
    </>
  );
}

const PAIRS_MEAN = [
  { key: "pairs", label: "pairs" },
  { key: "mean_m", label: "mean (m)" },
];

function Effects({ runs }: { runs: Runs }) {
  const bySubtype = (section: string, fields: Group["fields"], label = (s: string) => s): Group[] =>
    runs.effect_by_subtype.map((s, j) => ({
      label: label(s.subtype),
      path: `effect_by_subtype.${j}.${section}.per_match`,
      fields,
    }));
  return (
    <section data-section="per-match-effects">
      <h2>The same, per match</h2>
      <p>Every pooled figure above is the pooling of these rows.</p>
      <PerMatch
        runs={runs}
        id="marker"
        caption="Marker, run minus placebo"
        groups={[
          { label: "all runs", path: "instrument.marker.per_match", fields: PAIRS_MEAN },
          ...bySubtype("marker", PAIRS_MEAN),
        ]}
      />
      <PerMatch
        runs={runs}
        id="line"
        caption="Line (secondary), run minus placebo"
        groups={runs.effect_by_subtype.map((s, j) => ({
          label: `${s.subtype} (${s.line.testability})`,
          path: `effect_by_subtype.${j}.line.per_match`,
          fields: PAIRS_MEAN,
        }))}
      />
      <PerMatch
        runs={runs}
        id="pre-trend"
        caption="Pre-trend against effect (M3), on the pairs with both"
        groups={bySubtype("pre_trend", [
          { key: "pairs", label: "pairs" },
          { key: "pre_trend_mean_m", label: "pre-trend (m)" },
          { key: "effect_mean_m", label: "effect (m)" },
        ])}
      />
      <PerMatch
        runs={runs}
        id="fully-detected"
        caption="Marker detected in the whole window (M4)"
        groups={bySubtype("fully_detected", PAIRS_MEAN)}
      />
    </section>
  );
}

function Calibration({ runs }: { runs: Runs }) {
  const calibration = runs.funnel.coverage.flatMap((row, j) =>
    row.half === "calibration" ? [j] : [],
  );
  const powerRows = runs.power.rows.flatMap((row, j) => (row.half === "calibration" ? [j] : []));
  const counts = [
    "runs",
    "complete_windows",
    "runner_detected",
    "clean",
    "placebo_found",
    "analysis_set",
  ];
  return (
    <section data-section="calibration">
      <h2>Calibration, per match</h2>
      <p>
        The probes that ran before any effect was read (tasks 49 and 50), on the calibration half
        only.
      </p>
      <h3>Funnel: runs to pairs</h3>
      <Scroll>
        <thead>
          <tr>
            <th scope="col">match</th>
            {counts.map((c) => (
              <th scope="col" key={c}>
                {c.replaceAll("_", " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody data-table="funnel">
          {calibration.map((j) => (
            <tr key={j} data-match={runs.funnel.coverage[j].match_id}>
              <Td runs={runs} p={`funnel.coverage.${j}.match_id`} />
              {counts.map((c) => (
                <Td runs={runs} p={`funnel.coverage.${j}.${c}`} key={c} />
              ))}
            </tr>
          ))}
        </tbody>
      </Scroll>
      <h3>
        Power: the smallest effect that passes the bar in a share{" "}
        <F runs={runs} p="power.target_pass_rate" /> of simulated data sets, per subtype
      </h3>
      <Scroll>
        <thead>
          <tr>
            <th scope="col">subtype</th>
            <th scope="col">pairs</th>
            <th scope="col">units</th>
            <th scope="col">marker (placebo sd)</th>
            <th scope="col">line (placebo sd)</th>
          </tr>
        </thead>
        <tbody data-table="power">
          {powerRows.map((j) => (
            <tr key={j} data-subtype={runs.power.rows[j].subtype}>
              <td className="text">{runs.power.rows[j].subtype}</td>
              <Td runs={runs} p={`power.rows.${j}.pairs`} />
              <Td runs={runs} p={`power.rows.${j}.units`} />
              <Td runs={runs} p={`power.rows.${j}.mde80_marker_sd`} />
              <Td runs={runs} p={`power.rows.${j}.mde80_line_sd`} />
            </tr>
          ))}
        </tbody>
      </Scroll>
      <h3>Null: the bar on data sets built from placebos alone</h3>
      <p>
        At least one subtype passes in <F runs={runs} p="null.at_least_one_pct" /> % of them.
      </p>
      <PerMatch
        runs={runs}
        id="null"
        caption="Null, per match"
        groups={[
          {
            label: "null",
            path: "null.per_match",
            fields: [
              { key: "pairs", label: "pairs" },
              { key: "units", label: "units" },
              { key: "blocks", label: "blocks" },
              { key: "largest_block_share", label: "largest block share" },
            ],
          },
        ]}
      />
      <Scroll>
        <thead>
          <tr>
            <th scope="col">subtype</th>
            <th scope="col">pairs</th>
            <th scope="col">passes the bar in the null (%)</th>
          </tr>
        </thead>
        <tbody data-table="null-subtype">
          {runs.null.per_subtype.map((s, j) => (
            <tr key={s.subtype}>
              <td className="text">{s.subtype}</td>
              <Td runs={runs} p={`null.per_subtype.${j}.pairs`} />
              <Td runs={runs} p={`null.per_subtype.${j}.fires_pct`} />
            </tr>
          ))}
        </tbody>
      </Scroll>
    </section>
  );
}

function Held({ runs }: { runs: Runs }) {
  const opened = runs.never_opened.opened;
  const counts = ["runs", "runner_detected", "clean", "placebo_found", "analysis_set"];
  return (
    <section data-section="held-out" data-opened={String(opened)}>
      <h2>{opened ? "Held-out half: opened" : "Held-out half: never opened"}</h2>
      <p>
        {opened ? (
          <>The protocol was frozen and the held-out half read. Counts below.</>
        ) : (
          <>
            No outcome was computed on these matches and the protocol never left stage{" "}
            <F runs={runs} p="protocol.stage" />. Counts only.
          </>
        )}
      </p>
      <Scroll>
        <thead>
          <tr>
            <th scope="col">match</th>
            {counts.map((c) => (
              <th scope="col" key={c}>
                {c.replaceAll("_", " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody data-table="held-out">
          {runs.never_opened.counts.map((row, j) => (
            <tr key={row.match_id} data-match={row.match_id}>
              <Td runs={runs} p={`never_opened.counts.${j}.match_id`} />
              {counts.map((c) => (
                <Td runs={runs} p={`never_opened.counts.${j}.${c}`} key={c} />
              ))}
            </tr>
          ))}
        </tbody>
      </Scroll>
    </section>
  );
}

// The half second is the protocol's velocity window, the span the code shifts by; read, not typed.
const findings = (runs: Runs) => [
  {
    id: "frame-start",
    title: "The runner is already running when the provider's run begins",
    text: (
      <>
        The provider&apos;s frame_start is t_c. The columns compare the runner&apos;s speed at t_c
        with <F runs={runs} p="protocol.windows.velocity_s" /> s earlier.
      </>
    ),
    fields: [
      { key: "runner_running_at_tc_share", label: "running at t_c (share)" },
      {
        key: "runner_running_half_second_before_share",
        label: (
          <>
            running <F runs={runs} p="protocol.windows.velocity_s" /> s before (share)
          </>
        ),
      },
      { key: "runner_speed_at_tc_median_m_s", label: "speed at t_c (m/s)" },
      { key: "runner_speed_at_placebo_median_m_s", label: "speed at t' (m/s)" },
    ],
  },
  {
    id: "onset",
    title: "His own onset falls inside the pre-trend window",
    text: "The onset is the last frame at or before t_c below the onset speed. The columns place it against the window the pre-trend is measured over.",
    fields: [
      { key: "onset_median_s", label: "onset, median (s from t_c)" },
      { key: "onset_inside_pre_trend_window_share", label: "inside the pre-trend window (share)" },
      { key: "onset_before_pre_trend_window_share", label: "before it (share)" },
    ],
  },
  {
    id: "own-acceleration",
    title: "M3 cannot separate the run from its own acceleration",
    text: "The M3 statistic applied to the runner himself, who is not responding to anyone: his own pre-trend against his own effect.",
    fields: [
      { key: "runner_own_pre_trend_m", label: "runner's own pre-trend (m)" },
      { key: "runner_own_effect_m", label: "runner's own effect (m)" },
      { key: "runner_own_pre_trend_ratio", label: "runner's own ratio" },
    ],
  },
  {
    id: "marker-onset",
    title: "The marker's onset does not separate following from anticipating",
    text: "Where both had started before t_c, the share of pairs in which the marker started after the runner and the share in which he started before.",
    fields: [
      { key: "marker_after_runner_share", label: "marker after runner (share)" },
      { key: "marker_before_runner_share", label: "marker before runner (share)" },
      { key: "marker_onset_lag_median_s", label: "onset lag, median (s)" },
    ],
  },
];

function Reason({ runs }: { runs: Runs }) {
  const kin = runs.post_hoc_kinematics;
  return (
    <section data-section="reason">
      <h2>Why: a post hoc reading</h2>
      <p data-label="post-hoc">
        <strong>{kin.label}</strong>, written after the verdict. It decides nothing: M3, M4 and M5a
        stand as computed. Running is a speed of at least{" "}
        <F runs={runs} p="post_hoc_kinematics.thresholds.running_m_s" /> m/s; an onset is the last
        frame below <F runs={runs} p="post_hoc_kinematics.thresholds.onset_m_s" /> m/s.
      </p>
      {findings(runs).map((finding) => (
        <div key={finding.id} data-finding={finding.id}>
          <h3>{finding.title}</h3>
          <p>{finding.text}</p>
          <Scroll>
            <thead>
              <tr>
                <th scope="col">subtype</th>
                <th scope="col">pairs</th>
                {finding.fields.map((f) => (
                  <th scope="col" key={f.key}>
                    {f.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody data-table={`${finding.id}-pooled`}>
              {kin.per_subtype.map((s, j) => (
                <tr key={s.subtype} data-subtype={s.subtype}>
                  <td className="text">{s.subtype}</td>
                  <Td runs={runs} p={`post_hoc_kinematics.per_subtype.${j}.pooled.pairs`} />
                  {finding.fields.map((f) => (
                    <Td
                      runs={runs}
                      p={`post_hoc_kinematics.per_subtype.${j}.pooled.${f.key}`}
                      key={f.key}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </Scroll>
          <PerMatch
            runs={runs}
            id={`${finding.id}-per-match`}
            caption="Per match"
            groups={kin.per_subtype.map((s, j) => ({
              label: s.subtype,
              path: `post_hoc_kinematics.per_subtype.${j}.per_match`,
              fields: finding.fields,
            }))}
          />
        </div>
      ))}
    </section>
  );
}

function Protocol({ runs }: { runs: Runs }) {
  const p = runs.protocol;
  return (
    <section data-section="protocol">
      <h2>The protocol</h2>
      <p>
        <span data-fig="protocol.question">{p.question}</span>
      </p>
      <dl className="runs-protocol">
        <dt>stage</dt>
        <dd>
          <F runs={runs} p="protocol.stage" />, seen: {p.stages_seen.join(", ")}; frozen:{" "}
          {yes(p.frozen)}
        </dd>
        <dt>fingerprint</dt>
        <dd>
          <code data-fig="protocol.fingerprint">{p.fingerprint}</code>
        </dd>
        <dt>content sha256</dt>
        <dd>
          <code data-fig="protocol.content_sha256">{p.content_sha256}</code>
        </dd>
        <dt>calibration sha256</dt>
        <dd>
          <code data-fig="protocol.calibration_sha256">{p.calibration_sha256}</code>
        </dd>
        <dt>the bar</dt>
        <dd>
          calibration: <F runs={runs} p="protocol.bar.calibration.same_sign_matches_at_least" /> of{" "}
          <F runs={runs} p="protocol.bar.calibration.of_matches" /> matches with the same sign and
          p at most <F runs={runs} p="protocol.bar.calibration.p_at_most" />; held-out:{" "}
          <F runs={runs} p="protocol.bar.held_out.same_sign_matches_at_least" /> of{" "}
          <F runs={runs} p="protocol.bar.held_out.of_matches" /> and p at most{" "}
          <F runs={runs} p="protocol.bar.held_out.p_at_most" />
        </dd>
        <dt>history</dt>
        <dd>
          <ol>
            {p.history.map((h, j) => (
              <li key={`${h.task}-${j}`} data-history={j}>
                <F runs={runs} p={`protocol.history.${j}.stage`} />, task{" "}
                <F runs={runs} p={`protocol.history.${j}.task`} />,{" "}
                <F runs={runs} p={`protocol.history.${j}.date`} />
                {h.note ? (
                  <>
                    : <span data-fig={`protocol.history.${j}.note`}>{h.note}</span>
                  </>
                ) : null}
              </li>
            ))}
          </ol>
        </dd>
        <dt>artefacts</dt>
        <dd>
          {(["protocol", "calibration", "coverage"] as const).map((k, j) => (
            <span key={k}>
              {j > 0 ? " · " : ""}
              <code>{runs.sources[k]}</code>
            </span>
          ))}
        </dd>
      </dl>
    </section>
  );
}

function Scope({ runs }: { runs: Runs }) {
  const total = runs.funnel.coverage.length;
  const calibration = runs.funnel.coverage.filter((r) => r.half === "calibration").length;
  return (
    <p data-section="scope" className="runs-scope wrap">
      Scope: <span data-scope="matches">{total}</span> matches,{" "}
      <span data-scope="calibration">{calibration}</span> read as calibration and{" "}
      <span data-scope="held-out">{total - calibration}</span> set aside. It reports displacement
      in metres against a placebo; it ranks no player, team or run, and says nothing about what
      anyone meant to do.
    </p>
  );
}

export function RunsView({ runs }: { runs: Runs }) {
  return (
    <>
      <PageHead eyebrow="Off-ball runs">
        <h1>The run that moves nobody</h1>
        <Status runs={runs} />
      </PageHead>
      <Band dark>
        <RunsHook runs={runs} />
      </Band>
      <Band>
        <Stages runs={runs} />
        <Negative runs={runs} />
        <Effects runs={runs} />
        <Calibration runs={runs} />
        <Held runs={runs} />
        <Reason runs={runs} />
        <Protocol runs={runs} />
      </Band>
      {/* A child of main itself: the e2e reads the words of main's other children, and this line
          names what the page does not do. */}
      <Scope runs={runs} />
    </>
  );
}
