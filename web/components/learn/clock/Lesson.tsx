import type { ReactNode } from "react";
import { CLOCK, CLOCK_EXAMPLES } from "../../../lib/learn/clock-data";
import { clockFigures, type ClockFigures } from "../../../lib/learn/clock-figures";
import { qualityFigure } from "../../../lib/learn/gravity-data";
import { figureAt, matchFig } from "../../../lib/learn/json-figure";
import { HOOK, QUALITY } from "../../../lib/quality";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { ClockFit } from "./ClockFit";
import { ExposeFigures } from "./ExposeFigures";
import { PerMatch } from "./PerMatch";

// Lesson 6. No figure is typed: `c(path)` prints a value of clock.json, `q(path)` one of
// quality.json and `l(key)` one of `clockFigures`, each as a `data-fig` the e2e compares with its
// source.
const F = clockFigures(CLOCK, CLOCK_EXAMPLES, HOOK.g_data, HOOK.g_real);
const l = (key: keyof ClockFigures) => <Fig name={`learn.${key}`}>{String(F[key])}</Fig>;
const c = (path: string) => <Fig name={`clock.${path}`}>{String(figureAt(CLOCK, "clock", `clock.${path}`))}</Fig>;
const q = (path: string) => <Fig name={path}>{String(qualityFigure(QUALITY, path))}</Fig>;
const REPRO = "bb:114086";
const m = (field: string) => <Fig name={matchFig("clock", REPRO, field)}>{String(figureAt(CLOCK, "clock", matchFig("clock", REPRO, field)))}</Fig>;
const NATIVE = REPRO.replace(/^bb:/, "");

const sub = (x: string, i: ReactNode) => (
  <msub>
    <mi>{x}</mi>
    <mrow>{i}</mrow>
  </msub>
);
const bar = (x: string) => (
  <mover>
    <mi>{x}</mi>
    <mo>¯</mo>
  </mover>
);
const frac = (num: ReactNode, den: ReactNode) => (
  <mfrac>
    <mrow>{num}</mrow>
    <mrow>{den}</mrow>
  </mfrac>
);
const sum = (body: ReactNode) => (
  <>
    <msub>
      <mo>∑</mo>
      <mi>i</mi>
    </msub>
    {body}
  </>
);

export function Lesson({ sql }: { sql: string }) {
  return (
    <main className="page lesson learn-clock">
      <LessonHead n={6} title="Does the game clock keep the video's time?" level="Foundations">
        <p className="lede">
          Every basketball frame carries two clocks: the video&apos;s and the game&apos;s. Wherever the game clock runs for{" "}
          {l("min_seconds")}&nbsp;s or more, fit one against the other. In {l("cal_n")} matches the game clock moves{" "}
          {l("cal_lo")} to {l("cal_hi")} seconds for every second of video, match by match; in the other {l("ctl_n")},{" "}
          {l("ctl_lo")} to {l("ctl_hi")}. For the ball of the first lesson to fall at standard gravity it would have to move{" "}
          {l("slope_for_g")}.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            The first lesson found the ball falling slower than gravity, and left two suspects standing: the file&apos;s metres
            and the file&apos;s seconds. This lesson questions the seconds. SkillCorner&apos;s basketball tracking gives every
            frame a <code>wallClock</code>, <Quote id="skillcorner-wallclock" /> (<Cite id="skillcorner-wallclock" />), and a{" "}
            <code>gameClock</code>, <Quote id="skillcorner-gameclock" /> (<Cite id="skillcorner-gameclock" />). A third field says
            which frames to compare: <code>gameClockStopped</code> is <Quote id="skillcorner-gameclock-stopped" /> (
            <Cite id="skillcorner-gameclock-stopped" />
            ).
          </p>
          <p>
            The video clock steps by exactly one frame&apos;s time in {q("summary.ranges.clock_step_exact_basketball")}&nbsp;% of
            frames, which says it is regular, not that its second is a second. The game clock is another witness: it counts the
            game, not the video. If the video&apos;s seconds were too long or too short, the two would drift apart wherever the
            game clock runs. Do they?
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">A line through two clocks</h2>
          <p>
            Put the video&apos;s clock <M><mi>t</mi></M> on one axis and the game clock <M><mi>c</mi></M> on the other. While the
            game clock runs, a clock that keeps the video&apos;s time counts down one second per second: the points lie on a line
            of slope minus one. The first lesson fitted a parabola by least squares; this is the same fit with one degree less, a
            line, which <Quote id="nist-linear-ls" /> (<Cite id="nist-linear-ls" />) like the parabola. Written about the mean time{" "}
            <M>{bar("t")}</M> and the mean clock <M>{bar("c")}</M>, the slope is
          </p>
          <Formula label="The least-squares slope of the game clock on the video's clock">
            <mrow>
              <mi>b</mi>
              <mo>=</mo>
              {frac(
                sum(
                  <>
                    <mo>(</mo>
                    {sub("t", <mi>i</mi>)}
                    <mo>−</mo>
                    {bar("t")}
                    <mo>)</mo>
                    <mo>(</mo>
                    {sub("c", <mi>i</mi>)}
                    <mo>−</mo>
                    {bar("c")}
                    <mo>)</mo>
                  </>,
                ),
                sum(
                  <>
                    <msup>
                      <mrow>
                        <mo>(</mo>
                        {sub("t", <mi>i</mi>)}
                        <mo>−</mo>
                        {bar("t")}
                        <mo>)</mo>
                      </mrow>
                      <mn>2</mn>
                    </msup>
                  </>,
                ),
              )}
            </mrow>
          </Formula>
          <p>
            and the line passes through <M>{bar("t")}</M>, <M>{bar("c")}</M>. Centring changes nothing in exact arithmetic. It
            matters in a computer: the video&apos;s clock sits at hundreds or thousands of seconds, and a slope built from sums of
            its squares loses the digits that differ from frame to frame. What the line leaves over at each frame is the residual,
            in the handbook&apos;s words <Quote id="nist-residuals" /> (<Cite id="nist-residuals" />). If the line is the right
            model, the residuals are only the file&apos;s rounding.
          </p>
          <h3>What a wrong second would do</h3>
          <p>
            Suppose every second of video were <M><mi>s</mi></M> true seconds. A speed is a length over a time, so every speed
            measured in video seconds would be <M><mi>s</mi></M> times the true one. g is a length over a time squared:
          </p>
          <Formula label="A g measured in video seconds against the true g">
            <mrow>
              {sub("g", <mi>true</mi>)}
              <mo>=</mo>
              {frac(sub("g", <mi>video</mi>), <msup><mi>s</mi><mn>2</mn></msup>)}
            </mrow>
          </Formula>
          <p>
            The first lesson&apos;s shot gives g = {q("hook.g_data")}&nbsp;m/s². For it to be {q("hook.g_real")}, every time in the
            file would have to shrink by {l("shrink_pct")}&nbsp;%, and a true clock would move {l("slope_for_g")} seconds per
            second of video, not minus one. That is the size of drift to look for.
          </p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">One possession</h2>
          <p>
            The figure reads the clock of two published possessions. The first, of match {c("examples.0.match_id")}, runs for{" "}
            {l("cal_seconds")}&nbsp;s over {l("cal_frames")} frames, and the flag never says the clock stops. Fit every frame and
            the slope is {l("cal_slope")}. The residuals are {l("cal_rms_ms")}&nbsp;ms RMS and {l("cal_max_ms")}&nbsp;ms at most,
            against a file that writes the clock to {l("clock_unit_ms")}&nbsp;ms: what is left is the rounding.
          </p>
          <ClockFit examples={CLOCK_EXAMPLES} halfUnitMs={F.half_unit_ms} />
          <p>
            Now pick the second possession, of match {c("examples.1.match_id")}. Its clock is flat for its first frames, and a line
            through all {l("ctl_frames")} of them has slope {l("ctl_slope_all")}, with residuals of {l("ctl_rms_all_ms")}
            &nbsp;ms RMS. Least squares has no way to know which frames are wrong; it bends the line to all of them.
          </p>
          <p>
            Press From the flag. For its first {l("ctl_stopped_s")}&nbsp;s the provider&apos;s flag says the clock is stopped,
            and the fit now starts where the flag says it runs. The slope is {l("ctl_slope_flag")}: the clock is still flat for{" "}
            {l("ctl_hold_frames")} more frames, {l("ctl_hold_s")}&nbsp;s, after the flag says it runs. Press From the first move
            and the slope is {l("ctl_slope_move")}, with residuals of {l("ctl_rms_move_ms")}&nbsp;ms RMS. Where this clock moves,
            it moves at the video&apos;s rate; the drift came from the frames where it stood still.
          </p>
        </section>

        <section aria-labelledby="matches-h">
          <h2 id="matches-h">From one possession to ten matches</h2>
          <p>
            The pipeline cut every match into segments: runs of consecutive frames inside one period where the flag says the clock
            runs, {c("min_frames")} frames or more. That gives {l("seg_lo")} to {l("seg_hi")} segments per match,{" "}
            {l("segments")} in all, covering {l("minutes_lo")} to {l("minutes_hi")} minutes of each match. It fitted a line to
            each segment and took the median slope of the match, with its quartiles, so that a few odd segments cannot move it.
            The split into calibration and control matches is the one the quality checks made before this lesson, for other
            reasons.
          </p>
          <PerMatch matches={CLOCK.matches} held={F.held_pct} />
          <p>
            In the {l("cal_n")} calibration matches the median slope is {l("cal_lo")} to {l("cal_hi")}, and not one step inside a
            segment leaves the clock where it was: {l("cal_held")} held steps. The two clocks agree to within {l("cal_dev")}{" "}
            seconds per second, which would move g by {l("cal_g_pct")}&nbsp;%.
          </p>
          <p>
            In the {l("ctl_n")} control matches the median slope is {l("ctl_lo")} to {l("ctl_hi")}, and the clock holds on{" "}
            {l("ctl_held_lo")} to {l("ctl_held_hi")}&nbsp;% of the steps where the flag says it runs, as it did in the possession
            above. Read as a wrong second, the farthest of those medians would move g by {l("ctl_g_pct")}&nbsp;%, in the direction
            the first lesson would need. The first lesson needs {l("need_g_pct")}&nbsp;%.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            Every speed, acceleration and rate built from tracking takes its seconds from the file&apos;s clock. A second witness
            costs one regression per segment, and here it answers the question the first lesson could not: the game clock does
            not support a video second long enough to explain the low g.
          </p>
          <p>
            The control matches show the other half of the lesson. A summary of a slope is only as good as the frames that go into
            it: a flag that says the clock runs while it is still flat pulls a segment&apos;s slope away from the clock&apos;s own
            rate. Taking the median over many segments, and looking at the residuals of one, is what keeps that from being read as
            a drift.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              Both clocks come from the provider. Their agreement says the video&apos;s seconds and the game&apos;s are the same
              seconds; it cannot rule out an error both share.
            </li>
            <li>
              The test is of a scale on the video&apos;s clock. It says nothing about the file&apos;s metres, the other suspect of
              the first lesson.
            </li>
            <li>
              The flag decides which frames are compared. Why the clock stands still on some frames the flag calls running, in the
              control matches only, the files do not say; the lesson counts those frames and does not explain them.
            </li>
            <li>
              The published possessions write the clock to {l("clock_unit_ms")}&nbsp;ms; the table is computed at the
              provider&apos;s full precision.
            </li>
            <li>
              The quartiles are of segment slopes, not of frames: a short segment counts as much as a long one.
            </li>
            <li>Basketball only.</li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>
              On the second possession, move Fit from frame one frame at a time past the flat stretch. How fast does the slope
              recover, and why does the first frame after the move count for so much?
            </li>
            <li>
              On the first possession, find the frame whose residual is largest. What did the clock do there, a hundredth at a
              time?
            </li>
            <li>
              With pencil and paper: a clock that holds for a fifth of a segment and then runs true. What slope does a line through
              the whole segment give, roughly?
            </li>
            <li>
              Run the query below on another match: change the id in the file name and compare the result with that match&apos;s
              row in the table.
            </li>
          </ul>
        </section>

        <Reproduce sql={sql} browser="clock">
          <p>
            The query is the table&apos;s method in DuckDB, written for the public tracking file of match {c("examples.0.match_id")}.
            It reads the clock fields of every frame and nothing else, so it needs no Track Lab code and no intermediate tables.
          </p>
          <ol>
            <li>
              Clone <code>https://github.com/SkillCorner/opendata-basketball</code> with Git LFS, which holds the tracking
              files, and check out <code>4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66</code>.
            </li>
            <li>
              Open a terminal in <code>data/matches/{NATIVE}</code>, next to <code>{NATIVE}_tracking_data.jsonl.gz</code>.
            </li>
            <li>
              Save the query as <code>clock.sql</code> and run <code>duckdb &lt; clock.sql</code>.
            </li>
          </ol>
          <p>
            It returns {m("segments")} segments, {m("frames")} frames, {m("held")} held steps and a median slope of{" "}
            {m("slope_median")}, between {m("slope_q1")} and {m("slope_q3")}: that match&apos;s row in the table above. The same
            query, with only the id changed, gives every row; it was checked that way with DuckDB <code>1.5.5</code>.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="nist-linear-ls" full />: what makes a model linear, and why a line is fitted in closed form.
            </li>
            <li>
              <Cite id="nist-residuals" full />: residuals, and reading a fit from them.
            </li>
            <li>
              <Cite id="skillcorner-gameclock" full />: the provider&apos;s definitions of every field of a tracking frame.
            </li>
            <li>
              <a href="/learn/gravity">Does the ball obey gravity?</a>, the first lesson, for the low g and its two suspects, and{" "}
              <a href="/learn/coordinates">Can a court and a pitch share one table?</a> for the frame clock&apos;s own check.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures file={CLOCK} examples={CLOCK_EXAMPLES} g={HOOK.g_data} G={HOOK.g_real} />
    </main>
  );
}
