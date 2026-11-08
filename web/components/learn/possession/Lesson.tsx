import { DUCKDB_VERSION } from "../../../lib/platform";
import type { ReactNode } from "react";
import { figureAt } from "../../../lib/learn/json-figure";
import { POSSESSION } from "../../../lib/learn/possession-data";
import { lessonPossessionFigures, type PossessionLessonFigures } from "../../../lib/learn/possession-figures";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { ExposeFigures } from "./ExposeFigures";
import { PerMatch } from "./PerMatch";
import { Timeline } from "./Timeline";

// Lesson 10. No figure is typed: `p(path)` prints a value of possession.json, `l(key)` one of
// `lessonPossessionFigures`, `fb(key)` and `bb(key)` one of its two example matches, each as a
// `data-fig` the e2e compares with its source.
const F = lessonPossessionFigures(POSSESSION);
type Scalar = Exclude<keyof PossessionLessonFigures, "fb" | "bb" | "fb_ratio" | "bb_ratio">;
type One = PossessionLessonFigures["fb"];
const l = (key: Scalar) => <Fig name={`learn.${key}`}>{String(F[key])}</Fig>;
const fb = (key: keyof One) => <Fig name={`learn.fb.${key}`}>{String(F.fb[key])}</Fig>;
const bb = (key: keyof One) => <Fig name={`learn.bb.${key}`}>{String(F.bb[key])}</Fig>;
const p = (path: string) => <Fig name={`possession.${path}`}>{String(figureAt(POSSESSION, "possession", `possession.${path}`))}</Fig>;
const FB_ID = POSSESSION.football.timeline.match_id;
const BB_ID = POSSESSION.basketball.timeline.match_id;
const fbRow = (field: string) => p(`football.matches.${FB_ID}.${field}`);
const bbRow = (field: string) => p(`basketball.matches.${BB_ID}.${field}`);

const sub = (v: string, i: ReactNode) => (
  <msub>
    <mi>{v}</mi>
    <mrow>{i}</mrow>
  </msub>
);
const frac = (num: ReactNode, den: ReactNode) => (
  <mfrac>
    <mrow>{num}</mrow>
    <mrow>{den}</mrow>
  </mfrac>
);

export function Lesson({ sql }: { sql: string }) {
  return (
    <main id="main" className="page lesson learn-possession">
      <LessonHead
        n={10}
        title="How often does possession change hands?"
        level="Intermediate"
        result={[
          { label: "Football: median spell, per match", values: [F.fb_med_lo, F.fb_med_hi], unit: "s" },
          { label: "Basketball, on the video", values: [F.bb_med_lo, F.bb_med_hi], unit: "s" },
          { label: "Basketball, on the game clock", values: [F.bb_clk_med_lo, F.bb_clk_med_hi], unit: "s" },
        ]}
      >
        <p className="lede">
          A football team keeps the ball for a median of {l("fb_med_lo")} to {l("fb_med_hi")}&nbsp;s at a time, match by match.
          A basketball team keeps it for {l("bb_med_lo")} to {l("bb_med_hi")}&nbsp;s of video, or {l("bb_clk_med_lo")} to{" "}
          {l("bb_clk_med_hi")}&nbsp;s on the game clock, which leaves out the seconds it stands still. The median is half the
          story. The other half is the tail: how many spells last far longer, set against the one distribution in which the ball
          is as likely to change hands in any second as in the next. In basketball the two clocks give opposite
          answers in {l("bb_opposite")} of the {l("bb_matches")} matches.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            SkillCorner&apos;s basketball events have a table of possessions, and its dictionary defines the unit:{" "}
            <Quote id="skillcorner-possessions" /> (<Cite id="skillcorner-possessions" />
            ). Each one starts at a <code>startFrame</code>, <Quote id="skillcorner-possession-start" /> (
            <Cite id="skillcorner-possession-start" />
            ), and ends at an <code>endFrame</code>. It also carries the game clock at both ends: <code>startGameClock</code>,{" "}
            <Quote id="skillcorner-possession-clock-start" /> (<Cite id="skillcorner-possession-clock-start" />
            ), and <code>endGameClock</code>, the same at its end. That clock can stand still while the video runs on: the
            tracking marks each frame with <code>gameClockStopped</code>, <Quote id="skillcorner-gameclock-stopped" /> (
            <Cite id="skillcorner-gameclock-stopped" />
            ).
          </p>
          <p>
            The football files have no such table. They cut the match into phases of play instead: <Quote id="skillcorner-fb-phases" />{" "}
            (<Cite id="skillcorner-fb-phases" />
            ), and <Quote id="skillcorner-fb-phases-in-play" /> (<Cite id="skillcorner-fb-phases-in-play" />
            ). Their frames are those of the tracking: <Quote id="skillcorner-fb-frame" /> (<Cite id="skillcorner-fb-frame" />
            ). Their one time is a frame&apos;s <code>timestamp</code>, <Quote id="skillcorner-fb-timestamp" /> (
            <Cite id="skillcorner-fb-timestamp" />
            ), and no field says when that clock stops. How long does a team keep the ball before it changes hands, and does
            that time behave like a coin tossed every second?
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">Three units, and a distribution</h2>
          <p>
            Possession has more than one size. The smallest is one player&apos;s control of the ball, the touch of the{" "}
            <a href="/learn/dribble">ninth lesson</a>. The next is the provider&apos;s phase, a stretch of one team&apos;s play
            that the provider labels as a whole. The largest is the team&apos;s spell with the ball, from the moment it wins the
            ball to the moment it loses it. Basketball&apos;s possessions are that largest unit. In football the lesson builds it:
            a run is a stretch of consecutive phases of one period with the same team in possession, from the first frame of its
            first phase to the last frame of its last.
          </p>
          <p>
            A basketball possession has two durations, one per clock. On the video it runs from its first frame to its last. On
            the game clock it is the clock at its start minus the clock at its end, since that clock counts down:{" "}
            <Quote id="skillcorner-gameclock" /> (<Cite id="skillcorner-gameclock" />
            ). The video&apos;s duration counts every second the clock stands still inside the possession; the game clock&apos;s
            counts none. The lesson measures both. Football has the video&apos;s only.
          </p>
          <p>
            A run&apos;s duration <M>{sub("d", <mi>i</mi>)}</M> varies from one to the next, so the lesson treats the durations
            as a distribution: their median, their ninetieth percentile, and, to see the whole shape at once, the survival
            function, <Quote id="nist-survival" /> (<Cite id="nist-survival" />
            ). Estimated from <M><mi>N</mi></M> durations, it is the share that last longer than <M><mi>t</mi></M>:
          </p>
          <Formula label="The empirical survival function of the durations">
            <mrow>
              <mi>S</mi>
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <mo>=</mo>
              {frac(
                <>
                  <mo>#</mo>
                  <mo>{"{"}</mo>
                  <mi>i</mi>
                  <mo>:</mo>
                  {sub("d", <mi>i</mi>)}
                  <mo>&gt;</mo>
                  <mi>t</mi>
                  <mo>{"}"}</mo>
                </>,
                <mi>N</mi>,
              )}
            </mrow>
          </Formula>
          <p>
            A reference shape helps to read it. If the ball were as likely to change hands in any second as in the next, however
            long the team had held it, the durations would follow an exponential distribution, which{" "}
            <Quote id="nist-exponential" /> (<Cite id="nist-exponential" />
            ). With the same median <M><mi>m</mi></M> as the data, its survival function halves every <M><mi>m</mi></M> seconds:
          </p>
          <Formula label="The survival function of an exponential distribution with median m">
            <mrow>
              <msub>
                <mi>S</mi>
                <mi>exp</mi>
              </msub>
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <mo>=</mo>
              <msup>
                <mn>2</mn>
                <mrow>
                  <mo>−</mo>
                  <mi>t</mi>
                  <mo>/</mo>
                  <mi>m</mi>
                </mrow>
              </msup>
            </mrow>
          </Formula>
          <p>
            Under it, {l("exp_beyond2_pct")}&nbsp;% of spells outlast twice the median, and the ninetieth percentile is{" "}
            {l("exp_ratio")} times the median, whatever the median is. A data set whose ninetieth percentile sits further out has
            a longer tail than the exponential: more spells that go on and on than a constant chance per second would give.
          </p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">Two matches</h2>
          <p>
            The figure draws one match of each sport, a bar per spell in its team&apos;s colour. Football match{" "}
            {p("football.timeline.match_id")} has {fb("n")} runs over its {fb("periods")} periods: the median lasts {fb("median")}
            &nbsp;s and the ninetieth percentile {fb("p90")}&nbsp;s, {fb("ratio")} times the median. {fb("beyond2_pct")}&nbsp;% of
            the runs outlast twice the median, where the exponential gives {fb("exp_beyond2_pct")}, and {fb("beyond4_pct")}&nbsp;%
            outlast four times, against {fb("exp_beyond4_pct")}. Its longest run lasts {fb("longest")}&nbsp;s across{" "}
            {fb("longest_phases")} phases.
          </p>
          <Timeline timelines={{ football: POSSESSION.football.timeline, basketball: POSSESSION.basketball.timeline }} />
          <p>
            Basketball match {p("basketball.timeline.match_id")} has {bb("n")} possessions over {bb("periods")} periods, with a
            median of {bb("median")}&nbsp;s and a ninetieth percentile of {bb("p90")}&nbsp;s, {bb("ratio")} times the median.{" "}
            {bb("beyond2_pct")}&nbsp;% outlast twice the median and {bb("beyond4_pct")}&nbsp;% four times: on the video&apos;s time
            the curve and the exponential nearly meet. On the game clock the same possessions have a median of{" "}
            {bbRow("clock_median_s")}&nbsp;s and a ninetieth percentile of {bbRow("clock_p90_s")}&nbsp;s,{" "}
            {bbRow("clock_p90_over_median")} times the median, far short of the exponential&apos;s {l("exp_ratio")}: the near
            meeting is the video&apos;s. In the football match the curve sits above the exponential in its tail.
          </p>
        </section>

        <section aria-labelledby="matches-h">
          <h2 id="matches-h">From two matches to ten of each</h2>
          <p>
            The pipeline measured every match of each sport the same way. Each row of the tables is one match.
          </p>
          <PerMatch football={POSSESSION.football.matches} basketball={POSSESSION.basketball.matches} ratios={F} />
          <p>
            In football, {l("fb_phases_lo")} to {l("fb_phases_hi")} phases per match make {l("fb_runs_lo")} to {l("fb_runs_hi")}{" "}
            runs, {l("fb_runs")} in all. The median run lasts {l("fb_med_lo")} to {l("fb_med_hi")}&nbsp;s and the ninetieth
            percentile {l("fb_p90_lo")} to {l("fb_p90_hi")}&nbsp;s. {l("fb_multi_lo")} to {l("fb_multi_hi")}&nbsp;% of the runs
            span more than one phase: a phase is not a possession, and counting phases would cut a team&apos;s spells into
            pieces.
          </p>
          <p>
            In basketball, {l("bb_n_lo")} to {l("bb_n_hi")} possessions per match, {l("bb_possessions")} in all, last a median of{" "}
            {l("bb_med_lo")} to {l("bb_med_hi")}&nbsp;s, with the ninetieth percentile at {l("bb_p90_lo")} to {l("bb_p90_hi")}
            &nbsp;s. On the game clock the median is {l("bb_clk_med_lo")} to {l("bb_clk_med_hi")}&nbsp;s and the ninetieth
            percentile {l("bb_clk_p90_lo")} to {l("bb_clk_p90_hi")}&nbsp;s.
          </p>
          <p>
            The ninetieth percentile over the median is {l("fb_ratio_lo")} to {l("fb_ratio_hi")} in football and{" "}
            {l("bb_ratio_lo")} to {l("bb_ratio_hi")} in basketball, against the exponential&apos;s {l("exp_ratio")}. It is above
            the exponential&apos;s in {l("fb_above")} of the {l("fb_matches")} football matches and in {l("bb_above")} of the{" "}
            {l("bb_matches")} basketball ones.
          </p>
          <p>
            On the game clock basketball&apos;s answer turns over. Its ratio is {l("bb_clk_ratio_lo")} to {l("bb_clk_ratio_hi")},
            above the exponential&apos;s in {p("basketball.clock_above_exp")} of the {l("bb_matches")} matches: on the clock few
            possessions run far past their median, fewer than a constant chance per second would give. While it runs, the game
            clock keeps close to the video&apos;s time, as the <a href="/learn/clock">sixth lesson</a> measures, so the two part
            where the clock stands still. The video counts those stoppages, and they make its long tail.
          </p>
          <p>
            The lesson stops at the comparison. A tail longer or shorter than the exponential&apos;s says the chance of the ball
            changing hands is not the same in every second of every spell; it does not say why, and ten matches of each sport
            are not where to say it.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            The unit decides the figure. In football a phase, a run and one player&apos;s touch are all possession, and each
            gives its own median; a figure for possession that does not name its unit cannot be compared with another. So does
            the clock: the same basketball possessions have a long tail on the video and a short one on the game clock.
          </p>
          <p>
            And a median is not a distribution. The exponential of the reference has the same median as the data by
            construction, and still the two part ways in the tail. The survival curve shows the whole shape on one axis, and a
            model with one parameter is the simplest thing to set it against.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              Football&apos;s times are the video&apos;s, from a unit&apos;s first frame to its last: no field of its files says
              when the clock stops, so a stoppage inside a run counts, and so does the dead ball between two of its phases. Basketball&apos;s are
              measured on both clocks, and the figure&apos;s curves are the video&apos;s only.
            </li>
            <li>
              The phases, their frames and the team in possession of each are the provider&apos;s; so are the basketball
              possessions. The lesson joins phases into runs and adds nothing else.
            </li>
            <li>A phase with no team in possession ends the run before it and starts none.</li>
            <li>
              The game clock&apos;s figures leave out the basketball possessions without a clock at one end:{" "}
              {l("bb_clk_missing")} of the {l("bb_possessions")}.
            </li>
            <li>Football uses ten public matches, the ones in the tables; this lesson never reads the others.</li>
            <li>
              The exponential is a reference fitted by its median alone. The lesson fits no model, tests none and says nothing of
              how a spell ends.
            </li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>In the figure, switch to basketball. Where do the two curves part, and which one is above in the tail?</li>
            <li>In the football lanes, find the longest bar. How many phases does the text say it spans?</li>
            <li>
              With pencil and paper: under an exponential with median <M><mi>m</mi></M>, what share of spells outlast three
              times the median? And what does that share become if a spell has already lasted <M><mi>m</mi></M>?
            </li>
            <li>
              Run the queries below on another match of the tables: change the id in both names of a query and compare the
              result with that match&apos;s row.
            </li>
          </ul>
        </section>

        <Reproduce sql={sql} browser="possession">
          <p>
            The two queries are the tables&apos; method in DuckDB, one per sport, written for the public files of football match{" "}
            {p("football.timeline.match_id")} and basketball match {p("basketball.timeline.match_id")}. The football query reads
            five columns of the phases file and no other; neither needs Track Lab code or an intermediate table.
          </p>
          <ol>
            <li>
              Clone <code>https://github.com/SkillCorner/opendata</code> and check out{" "}
              <code>4340d274572876239c154c90bc507a9b3250a656</code>; clone{" "}
              <code>https://github.com/SkillCorner/opendata-basketball</code> with Git LFS next to it and check out{" "}
              <code>4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66</code>.
            </li>
            <li>Open a terminal in the folder that holds both.</li>
            <li>
              Save the queries as <code>possession.sql</code> and run <code>duckdb &lt; possession.sql</code>.
            </li>
          </ol>
          <p>
            The first returns {fbRow("phases")} phases and {fbRow("runs")} runs, a median of {fbRow("run_median_s")}&nbsp;s, a
            ninetieth percentile of {fbRow("run_p90_s")}&nbsp;s and {fbRow("multi_phase_pct")}&nbsp;% of runs over more than one
            phase; the second, {bbRow("possessions")} possessions, a median of {bbRow("median_s")}&nbsp;s and a ninetieth
            percentile of {bbRow("p90_s")}&nbsp;s on the video, then {bbRow("clock_possessions")} with a game clock at both
            ends, a median of {bbRow("clock_median_s")}&nbsp;s and a ninetieth percentile of {bbRow("clock_p90_s")}&nbsp;s on
            it: those matches&apos; rows in the tables above. The same queries, with only the
            ids changed, give every row; they were checked that way with DuckDB <code>{DUCKDB_VERSION}</code>.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="nist-survival" full /> and <Cite id="nist-exponential" full />: the survival function and the distribution
              of a constant rate.
            </li>
            <li>
              <Cite id="skillcorner-possessions" full />: the provider&apos;s definitions of every field of a possession.
            </li>
            <li>
              <a href="/learn/clock">Does the game clock keep the video&apos;s time?</a>, the sixth lesson, for the two clocks a
              duration can be measured on.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures file={POSSESSION} />
    </main>
  );
}
