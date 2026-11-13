import { DUCKDB_VERSION } from "../../../lib/platform";
import type { ReactNode } from "react";
import { qualityFigure } from "../../../lib/learn/gravity-data";
import { SPEED, SPEED_EXAMPLE, speedFig, speedFigure } from "../../../lib/learn/speed-data";
import { speedFigures, type SpeedFigures } from "../../../lib/learn/speed-figures";
import { QUALITY } from "../../../lib/quality";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { ExposeFigures } from "./ExposeFigures";
import { PerMatch } from "./PerMatch";
import { TracePlot } from "./TracePlot";
import { WindowPlot } from "./WindowPlot";

// Lesson 2. No figure is typed: `s(path)` prints a value of speed.json, `q(path)` one of
// quality.json and `l(key)` one of `speedFigures`, each as a `data-fig` the e2e compares with its
// source.
const F = speedFigures(SPEED_EXAMPLE, SPEED);
const l = (key: keyof SpeedFigures) => <Fig name={`learn.${key}`}>{F[key]}</Fig>;
const s = (path: string) => <Fig name={`speed.${path}`}>{String(speedFigure(SPEED, `speed.${path}`))}</Fig>;
const q = (path: string) => <Fig name={path}>{String(qualityFigure(QUALITY, path))}</Fig>;
const m = (match_id: string, field: string) => <Fig name={speedFig(match_id, field)}>{String(speedFigure(SPEED, speedFig(match_id, field)))}</Fig>;
const REPRO = SPEED.example.match_id;

const sub = (x: string, i: ReactNode) => (
  <msub>
    <mi>{x}</mi>
    <mrow>{i}</mrow>
  </msub>
);
const frac = (num: ReactNode, den: ReactNode) => (
  <mfrac>
    <mrow>{num}</mrow>
    <mrow>{den}</mrow>
  </mfrac>
);
const xAt = (shift: ReactNode) => (
  <>
    <mi>x</mi>
    <mo>(</mo>
    <mi>t</mi>
    {shift}
    <mo>)</mo>
  </>
);
const plusH = (
  <>
    <mo>+</mo>
    <mi>h</mi>
  </>
);
const minusH = (
  <>
    <mo>−</mo>
    <mi>h</mi>
  </>
);
// x′, x″, x‴: the derivatives, written as one identifier so the primes sit on the x.
const prime = (n: number) => <mi>{`x${["′", "″", "‴"][n - 1]}`}</mi>;
// The position at frame n plus a shift.
const xn = (shift: ReactNode) => (
  <>
    <mi>x</mi>
    <mo>(</mo>
    <mi>n</mi>
    {shift}
    <mo>)</mo>
  </>
);

export function Lesson({ sql }: { sql: string }) {
  return (
    <main id="main" className="page lesson learn-speed">
      <LessonHead
        n={2}
        title="Where does the provider's speed come from?"
        level="Foundations"
        result={[{ label: "Median gap to a centred difference", values: [F.gap_lo, F.gap_hi], unit: "m/s" }]}
      >
        <p className="lede">
          SkillCorner&apos;s basketball files give every player a speed in every frame, next to the position. Put it beside
          the simplest centred difference of the same positions and the two agree to within {l("gap_lo")} to{" "}
          {l("gap_hi")}&nbsp;m/s, median per match. The field behaves like the positions again, differentiated.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            Each frame of the basketball tracking holds, for every player on court, a position in feet and a field called{" "}
            <code>speed</code>, which the provider&apos;s dictionary defines as <Quote id="skillcorner-speed" /> (
            <Cite id="skillcorner-speed" />). Positions arrive {s("fps")} times a second, so a speed can also be worked
            out from them: how far the player moved between two frames, over the time between them.
          </p>
          <p>
            So is the field a second measurement, taken some other way, or something that behaves like the positions again, differentiated? The answer
            matters to anyone who checks one with the other. A field computed from the positions cannot confirm them. This
            lesson builds the three simplest estimates of speed from positions, sizes their errors, and puts each beside the
            field, match by match.
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">Finite differences</h2>
          <p>
            Write a player&apos;s position along one axis as <M>{xAt(null)}</M> and the time between two frames as{" "}
            <M><mi>h</mi></M>, here {l("step_ms")}&nbsp;ms. Three differences estimate the velocity at time{" "}
            <M><mi>t</mi></M>: forward, backward and central.
          </p>
          <Formula label="The forward, backward and central differences">
            <mtable>
              <mtr>
                <mtd>
                  <mrow>
                    {sub("v", <mi>f</mi>)}
                    <mo>=</mo>
                    {frac(
                      <>
                        {xAt(plusH)}
                        <mo>−</mo>
                        {xAt(null)}
                      </>,
                      <mi>h</mi>,
                    )}
                  </mrow>
                </mtd>
              </mtr>
              <mtr>
                <mtd>
                  <mrow>
                    {sub("v", <mi>b</mi>)}
                    <mo>=</mo>
                    {frac(
                      <>
                        {xAt(null)}
                        <mo>−</mo>
                        {xAt(minusH)}
                      </>,
                      <mi>h</mi>,
                    )}
                  </mrow>
                </mtd>
              </mtr>
              <mtr>
                <mtd>
                  <mrow>
                    {sub("v", <mi>c</mi>)}
                    <mo>=</mo>
                    {frac(
                      <>
                        {xAt(plusH)}
                        <mo>−</mo>
                        {xAt(minusH)}
                      </>,
                      <>
                        <mn>2</mn>
                        <mi>h</mi>
                      </>,
                    )}
                  </mrow>
                </mtd>
              </mtr>
            </mtable>
          </Formula>
          <p>They look alike and are not. Expand the position around <M><mi>t</mi></M>, a Taylor series:</p>
          <Formula label="The Taylor series of the position a step either side of t">
            <mrow>
              {xAt(
                <>
                  <mo>±</mo>
                  <mi>h</mi>
                </>,
              )}
              <mo>=</mo>
              {xAt(null)}
              <mo>±</mo>
              <mi>h</mi>
              {prime(1)}
              <mo>+</mo>
              {frac(
                <msup>
                  <mi>h</mi>
                  <mn>2</mn>
                </msup>,
                <mn>2</mn>,
              )}
              {prime(2)}
              <mo>±</mo>
              {frac(
                <msup>
                  <mi>h</mi>
                  <mn>3</mn>
                </msup>,
                <mn>6</mn>,
              )}
              {prime(3)}
              <mo>+</mo>
              <mo>…</mo>
            </mrow>
          </Formula>
          <p>and put it into each difference:</p>
          <Formula label="The leading error of the forward and the central difference">
            <mtable>
              <mtr>
                <mtd>
                  <mrow>
                    {sub("v", <mi>f</mi>)}
                    <mo>=</mo>
                    {prime(1)}
                    <mo>+</mo>
                    {frac(<mi>h</mi>, <mn>2</mn>)}
                    {prime(2)}
                    <mo>+</mo>
                    <mo>…</mo>
                  </mrow>
                </mtd>
              </mtr>
              <mtr>
                <mtd>
                  <mrow>
                    {sub("v", <mi>c</mi>)}
                    <mo>=</mo>
                    {prime(1)}
                    <mo>+</mo>
                    {frac(
                      <msup>
                        <mi>h</mi>
                        <mn>2</mn>
                      </msup>,
                      <mn>6</mn>,
                    )}
                    {prime(3)}
                    <mo>+</mo>
                    <mo>…</mo>
                  </mrow>
                </mtd>
              </mtr>
            </mtable>
          </Formula>
          <p>
            The forward and backward differences are off by a term in <M><mi>h</mi></M> times the acceleration,{" "}
            <M>{prime(2)}</M>, with opposite signs. In the central one the acceleration cancels and the first error left is
            in <M>
              <msup>
                <mi>h</mi>
                <mn>2</mn>
              </msup>
            </M>
            . That leftover is the truncation error, and the central difference is the three-point formula of numerical
            differentiation at its middle node (<Cite id="dlmf-differentiation" />).
          </p>
          <p>
            There is a plainer way to see it. The forward difference is the slope of the chord from <M><mi>t</mi></M> to{" "}
            <M>
              <mi>t</mi>
              <mo>+</mo>
              <mi>h</mi>
            </M>
            , and at constant acceleration a chord&apos;s slope is the speed at its middle: half a frame, {l("half_step_ms")}
            &nbsp;ms, late. The backward difference is as early. The central difference straddles its frame. A synthetic
            makes it concrete: a body speeding up at {l("synth_accel")}&nbsp;m/s², sampled {s("fps")} times a second. The
            forward difference misses its speed by {l("synth_forward_gap")}&nbsp;m/s at every frame and the central one by{" "}
            {l("synth_central_gap")}. On a parabola in time, the curve the first lesson fitted, it is exact.
          </p>

          <h3>Noise and rounding</h3>
          <p>
            A difference divides a small change of position by a small time, and it divides the position&apos;s errors by
            the same small time. If every position may be off by up to <M><mi>e</mi></M>, the errors at the two ends can
            add, so one axis of each difference may be off by
          </p>
          <Formula label="The most an error of e in every position can move each difference">
            <mrow>
              <mo>|</mo>
              <mi>Δ</mi>
              {sub("v", <mi>f</mi>)}
              <mo>|</mo>
              <mo>≤</mo>
              {frac(
                <>
                  <mn>2</mn>
                  <mi>e</mi>
                </>,
                <mi>h</mi>,
              )}
              <mo>,</mo>
              <mspace width="1em" />
              <mo>|</mo>
              <mi>Δ</mi>
              {sub("v", <mi>c</mi>)}
              <mo>|</mo>
              <mo>≤</mo>
              {frac(<mi>e</mi>, <mi>h</mi>)}
            </mrow>
          </Formula>
          <p>
            The site publishes its possessions with positions rounded to {l("resolution_cm")}&nbsp;cm, so{" "}
            <M><mi>e</mi></M> is half of that. At {s("fps")} frames a second one axis of the central difference can be off by{" "}
            {l("bound_central")}&nbsp;m/s and the forward one by {l("bound_forward")}; the two axes together move the
            central speed by up to {l("bound_central_speed")}. A shorter step lowers the truncation error and raises this
            one, a longer step does the reverse, and averaging is the usual way between them.
          </p>

          <h3>Moving averages and Savitzky-Golay</h3>
          <p>
            Count time in frames, so that <M>{xn(null)}</M> is the position at frame <M><mi>n</mi></M>, and average{" "}
            <M><mi>k</mi></M> central differences centred on it, with <M><mi>k</mi></M> odd. Every position inside the
            window enters once with a plus and once with a minus, and what survives is a single difference across the
            window:
          </p>
          <div className="learn-speed-long">
          <Formula label="A moving average of k central differences is one longer difference">
            <mtable>
              <mtr>
                <mtd>
            <mrow>
              {frac(<mn>1</mn>, <mi>k</mi>)}
              <msubsup className="sum-limits">
                <mo>∑</mo>
                <mrow>
                  <mi>j</mi>
                  <mo>=</mo>
                  <mo>−</mo>
                  <mi>m</mi>
                </mrow>
                <mi>m</mi>
              </msubsup>
              {frac(
                <>
                  {xn(<><mo>+</mo><mi>j</mi><mo>+</mo><mn>1</mn></>)}
                  <mo>−</mo>
                  {xn(<><mo>+</mo><mi>j</mi><mo>−</mo><mn>1</mn></>)}
                </>,
                <>
                  <mn>2</mn>
                  <mi>h</mi>
                </>,
              )}
            </mrow>
                </mtd>
              </mtr>
              <mtr>
                <mtd>
            <mrow>
              <mo>=</mo>
              {frac(
                <>
                  {xn(<><mo>+</mo><mi>m</mi><mo>+</mo><mn>1</mn></>)}
                  <mo>+</mo>
                  {xn(<><mo>+</mo><mi>m</mi></>)}
                  <mo>−</mo>
                  {xn(<><mo>−</mo><mi>m</mi></>)}
                  <mo>−</mo>
                  {xn(<><mo>−</mo><mi>m</mi><mo>−</mo><mn>1</mn></>)}
                </>,
                <>
                  <mn>2</mn>
                  <mi>k</mi>
                  <mi>h</mi>
                </>,
              )}
            </mrow>
                </mtd>
              </mtr>
            </mtable>
          </Formula>
          </div>
          <p>
            Here <M>
              <mi>k</mi>
              <mo>=</mo>
              <mn>2</mn>
              <mi>m</mi>
              <mo>+</mo>
              <mn>1</mn>
            </M>
            . The noise falls as the window widens, and the truncation error grows with the span. Laurie Shaw&apos;s
            tracking code, a common starting point, smooths velocities this way. Its velocity function opens with{" "}
            <Quote id="shaw-velocities" /> (<Cite id="shaw-velocities" />), and its unsmoothed estimate is the backward
            difference, <Quote id="shaw-difference" /> (<Cite id="shaw-difference" />).
          </p>
          <p>
            A Savitzky-Golay filter fits, at every sample, a polynomial by least squares to the window around it and keeps
            its value at the middle; its order is <Quote id="scipy-savgol" /> (<Cite id="scipy-savgol" />). With order one
            the polynomial is a line, and the first lesson&apos;s centring settles the rest: in time measured from the
            middle sample the odd sums vanish, so the line&apos;s value there is the mean of the window. A Savitzky-Golay
            filter of order one is a moving average. Shaw&apos;s default is therefore an average of {s("shaw_window")}{" "}
            backward differences, which is one difference across the window, centred half a frame early.
          </p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">One player, one possession</h2>
          <p>
            Take one player through one of the possessions the <a href="/tracking/replay">replay</a> shows,
            in match {s("example.match_id")}: {l("frames")} frames, {l("duration_s")}&nbsp;s, with the player in every one.
            The fastest the file has the player going is {l("peak")}&nbsp;m/s. The positions are the published ones, at
            the centimetre; the speed is the file&apos;s own field, converted to metres per second.
          </p>
          <TracePlot example={SPEED_EXAMPLE} shawWindow={SPEED.shaw_window} />
          <p>
            Start with the central difference and no averaging. The white line lies on the cyan one: the median gap is{" "}
            {l("ex_central_median")}&nbsp;m/s over {l("ex_central_frames")} frames, and the largest is{" "}
            {l("ex_central_max")}, inside the {l("bound_central_speed")} the rounding allows. Switch to forward or backward
            and the median gap grows to {l("ex_forward_median")} and {l("ex_backward_median")}: the half frame either way,
            and a rounding bound twice as wide.
          </p>
          <p>
            Now widen the window. The gap falls to {l("ex_best_median")}&nbsp;m/s at <var>k</var> = {l("ex_best_k")} and
            climbs again, to {l("ex_k_max_median")} at <var>k</var> = {l("ex_k_max")}. The first windows average the
            rounding away; the wide ones start to flatten the player&apos;s own changes of pace. Shaw&apos;s recipe lands
            at {l("ex_shaw_median")}.
          </p>
          <p>
            The rounding makes the agreement look looser than it is. The same player over the same frames, at the
            file&apos;s full precision, gives a central gap of {s("example.full_precision.median_gap")}&nbsp;m/s, median over{" "}
            {s("example.full_precision.frames")} frames.
          </p>
        </section>

        <section aria-labelledby="matches-h">
          <h2 id="matches-h">From one player to every match</h2>
          <p>
            The pipeline ran the same comparison over every player row of the {l("matches")} basketball matches whose frames
            just before and just after are in the file, a triple, at the files&apos; own precision. Each row of the table
            is one match.
          </p>
          <PerMatch matches={SPEED.matches} />
          <p>
            In every match the correlation of the field with the central difference lies between {l("r_lo")} and{" "}
            {l("r_hi")}, and the median gap between {l("gap_lo")} and {l("gap_hi")}&nbsp;m/s. On the same rows the forward
            and backward differences sit at {l("one_sided_lo")} to {l("one_sided_hi")}, {l("one_sided_ratio_lo")} to{" "}
            {l("one_sided_ratio_hi")} times as far. The tail is
            longer: the gap that one row in a hundred exceeds is {l("p99_lo")} to {l("p99_hi")}&nbsp;m/s.
          </p>
          <p>
            The clock check on <a href="/engineering/quality">/engineering/quality</a> had already put the field next to the backward difference,
            and found their median ratio within {q("summary.ranges.clock_speed_mismatch")}&nbsp;% of one in every match.
            That says the field and the positions run on the same clock. The table answers the next question: of the
            three differences, the field follows the centred one.
          </p>
          <WindowPlot example={SPEED_EXAMPLE} file={SPEED} />
          <p>
            Averaging takes the agreement further. At the files&apos; precision the median gap is smallest at{" "}
            <var>k</var> = {l("best_k")} in {l("best_k_matches")} of {l("matches")} matches, at {l("best_lo")} to{" "}
            {l("best_hi")}&nbsp;m/s, against {l("gap_lo")} to {l("gap_hi")} for the plain central difference. The field
            behaves like a centred derivative of the positions taken over a few frames each side.
          </p>
        </section>

        <section aria-labelledby="not-h">
          <h2 id="not-h">What does not explain it</h2>
          <h3>Smooth motion alone</h3>
          <p>
            If players moved smoothly enough, all three differences would sit close to any speed taken from the same
            positions, and the table could not tell them apart. It does tell them apart: on the same rows the forward and
            backward differences sit {l("one_sided_ratio_lo")} to {l("one_sided_ratio_hi")} times as far from the field as
            the central one. The field is centred on its own frame, not half a frame to either side.
          </p>
          <h3>Another unit or another clock</h3>
          <p>
            A speed in another unit, or per a different second, would scale every row and the gaps would be a fixed
            fraction of the speed. They are hundredths of a metre per second on speeds of several metres per second. The
            field uses the same feet and the same frame clock as the positions, which also means it cannot test either of
            them. That is the clock and ruler of the first lesson again.
          </p>
          <h3>Rounding</h3>
          <p>
            The per-match figures are taken at the files&apos; own precision, where the rounding of the published
            possessions does not enter. The gap shrinks there but does not vanish: the closest window still leaves{" "}
            {l("best_lo")} to {l("best_hi")}&nbsp;m/s. What makes the rest, another filter, a model that estimates position
            and speed together or something else, the files do not say.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            The field behaves like the positions again, not like a second witness. Comparing it with the positions tests whether the file agrees with itself,
            not whether the player was where the file says. A pipeline that validates positions against speed, or the
            other way round, learns about the provider&apos;s arithmetic.
          </p>
          <p>
            Every count built on speed rests on a recipe: time above a threshold, sprints, top speeds. Counted from the
            field it takes the provider&apos;s smoothing; from your own differences, yours. Shaw&apos;s recipe on these
            files lands {l("shaw_lo")} to {l("shaw_hi")}&nbsp;m/s from the field, median per match. That is small at the
            median; this lesson does not measure how the two part in the tails, where thresholds sit. Pick one recipe and
            keep it through an analysis, and say which.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              The field passes Shaw&apos;s limit of {s("max_speed")}&nbsp;m/s, <Quote id="shaw-maxspeed" /> (
              <Cite id="shaw-maxspeed" />), in {l("over_matches")} of {l("matches")} matches, in {l("over_rows")} of{" "}
              {l("all_rows")} player rows. The lesson gives these as counts and does not ask what produces them.
            </li>
            <li>Players only: the ball also has a speed field, and it is not compared here.</li>
            <li>The football files give players a position and no speed, so the comparison is basketball only.</li>
            <li>
              The example&apos;s positions are the published ones, rounded to {l("resolution_cm")}&nbsp;cm; every per-match
              figure uses the files&apos; full precision.
            </li>
            <li>
              The clock check&apos;s ratio is taken over its own selection of frames, described on /engineering/quality; this
              lesson&apos;s figures use every triple.
            </li>
            <li>
              Agreement with the positions says nothing about whether the positions are right. There is no outside
              reference for speed in these files.
            </li>
            <li>The cause of the gap that remains stays open.</li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>
              With no averaging, switch between forward and backward and look where the player speeds up or slows down.
              Which line runs ahead of the cyan one, and by how much time?
            </li>
            <li>Find the window with the smallest median gap, then push it to the end. Which part of the trace bends first?</li>
            <li>Press Shaw&apos;s recipe, then Plain central. Where do the two disagree most, and why there?</li>
            <li>
              With pencil and paper, average three central differences and watch the inner positions cancel. Then fit a
              line by least squares to five equally spaced samples and check that its middle value is their mean.
            </li>
            <li>
              Run the query below on another match: change the id in the file name and compare the result with that
              match&apos;s row in the table.
            </li>
          </ul>
        </section>

        <Reproduce sql={sql} browser="speed">
          <p>
            The query is the comparison of the table in DuckDB, written for the public tracking file of match{" "}
            {s("example.match_id")}. It needs nothing else: no Pitch & Parquet code and no intermediate tables.
          </p>
          <ol>
            <li>
              Clone <code>https://github.com/SkillCorner/opendata-basketball</code> with Git LFS, which holds the
              tracking files, and check out <code>4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66</code>.
            </li>
            <li>
              Open a terminal in <code>data/matches/{SPEED.example.match_id.replace(/^bb:/, "")}</code>, next to{" "}
              <code>{SPEED.example.match_id.replace(/^bb:/, "")}_tracking_data.jsonl.gz</code>.
            </li>
            <li>
              Save the query as <code>speed.sql</code> and run <code>duckdb &lt; speed.sql</code>.
            </li>
          </ol>
          <p>
            It returns {m(REPRO, "triples")} triples, a correlation of {m(REPRO, "r")} and a median gap of{" "}
            {m(REPRO, "median_gap")}&nbsp;m/s, that match&apos;s row in the table above. The same query, with only the id
            changed, gives the first three figures of every row; it was checked that way with DuckDB <code>{DUCKDB_VERSION}</code>.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="dlmf-differentiation" full />: the two- and three-point formulas and their remainders.
            </li>
            <li>
              <Cite id="scipy-savgol" full />: the Savitzky-Golay filter as most Python code calls it.
            </li>
            <li>
              <Cite id="shaw-velocities" full />: a complete velocity recipe for tracking data, short enough to read in one
              sitting.
            </li>
            <li>
              <Cite id="skillcorner-speed" full />: the provider&apos;s definitions of every field in the tracking files.
            </li>
            <li>
              <a href="/learn/gravity">Does the ball obey gravity?</a>, the first lesson, for least squares and centring;{" "}
              <a href="/engineering/quality">/engineering/quality</a> and the <a href="/engineering/bulletin">bulletin</a> for the clock check.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures example={SPEED_EXAMPLE} file={SPEED} />
    </main>
  );
}
