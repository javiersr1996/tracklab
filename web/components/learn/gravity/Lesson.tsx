import type { ReactNode } from "react";
import { GRAVITY_HOOK, GRAVITY_MATCHES, qualityFigure } from "../../../lib/learn/gravity-data";
import { lessonFigures, type LessonFigures } from "../../../lib/learn/lesson-figures";
import { QUALITY } from "../../../lib/quality";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { ExposeFigures } from "./ExposeFigures";
import { FitPlot } from "./FitPlot";
import { NoiseStrip } from "./NoiseStrip";
import { PerMatch } from "./PerMatch";
import { WindowPlot } from "./WindowPlot";

// Lesson 1 (task 80). No figure is typed: `q(path)` prints a value of `quality.json` and `l(key)`
// one of `lessonFigures`, each as a `data-fig` the e2e compares with its source. The sums in the
// formulas run over the samples of one window.
const F = lessonFigures(GRAVITY_HOOK, GRAVITY_MATCHES);
const l = (key: keyof LessonFigures) => <Fig name={`learn.${key}`}>{F[key]}</Fig>;
const q = (path: string) => <Fig name={path}>{String(qualityFigure(QUALITY, path))}</Fig>;
const G = q("hook.g_real");

const sub = (x: string, i: string) => (
  <msub>
    <mi>{x}</mi>
    <mi>{i}</mi>
  </msub>
);
const sum = (i = "i") => (
  <msub>
    <mo>∑</mo>
    <mi>{i}</mi>
  </msub>
);
const pow = (base: ReactNode, n: string) => (
  <msup>
    {base}
    <mn>{n}</mn>
  </msup>
);
// The sum of u to the k over the window, in brackets: n itself when k is zero.
const sumU = (k: number) =>
  k === 0 ? (
    <mi>n</mi>
  ) : (
    <mrow>
      <mo>(</mo>
      <mo>∑</mo>
      {k === 1 ? <mi>u</mi> : pow(<mi>u</mi>, String(k))}
      <mo>)</mo>
    </mrow>
  );

export function Lesson({ sql }: { sql: string }) {
  return (
    <main className="page lesson">
      <LessonHead n={1} title="Does the ball obey gravity?" level="Foundations">
        <p className="lede">
          Fit a parabola to a basketball&apos;s height in flight and it tells you the gravity the ball fell under. In
          SkillCorner&apos;s open basketball tracking that gravity comes out far below {G}&nbsp;m/s². The ball falls as if
          the Earth were lighter.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            Between the hand and the rim a basketball is in free flight. Leave the air out and its height is a parabola
            in time, with a curvature set by gravity alone. That turns every shot in a tracking file into a small
            experiment with a known answer: the standard acceleration of gravity, {G}&nbsp;m/s², the conventional value the
            General Conference on Weights and Measures adopted (<Cite id="cgpm-1901" />) and CODATA keeps as exact (
            <Cite id="codata-gn" />).
          </p>
          <p>
            So the question is plain: take the heights a tracking provider reports for a ball in flight, ask what
            gravity they imply, and see whether that number comes back. In SkillCorner&apos;s open basketball data it
            does not, by a wide margin and in the same direction in every match. Why is a harder question; this lesson
            rules some causes out and leaves the rest open.
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">A parabola by least squares</h2>
          <p>Write the height of the ball as a function of time:</p>
          <Formula label="The height of the ball as a parabola in time">
            <mrow>
              <mi>z</mi>
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <mo>=</mo>
              <mi>c</mi>
              <mo>+</mo>
              <mi>b</mi>
              <mi>t</mi>
              <mo>+</mo>
              <mi>a</mi>
              {pow(<mi>t</mi>, "2")}
            </mrow>
          </Formula>
          <p>
            Gravity enters only through <M><mi>a</mi></M>. A body falling freely has{" "}
            <M>
              <mi>a</mi>
              <mo>=</mo>
              <mo>−</mo>
              <mi>g</mi>
              <mo>/</mo>
              <mn>2</mn>
            </M>
            , so{" "}
            <M>
              <mi>g</mi>
              <mo>=</mo>
              <mo>−</mo>
              <mn>2</mn>
              <mi>a</mi>
            </M>
            . The other two, where the ball was and how fast it rose at time zero, do not matter here.
          </p>
          <p>
            A tracker gives heights <M>{sub("z", "i")}</M> at times <M>{sub("t", "i")}</M>, far more than the three a
            parabola needs, and no parabola passes through all of them. Least squares picks the one with the smallest
            sum of squared residuals:
          </p>
          <Formula label="The sum of squared residuals the fit minimises">
            <mrow>
              <mi>S</mi>
              <mo>=</mo>
              {sum()}
              {pow(
                <mrow>
                  <mo>(</mo>
                  {sub("z", "i")}
                  <mo>−</mo>
                  <mi>c</mi>
                  <mo>−</mo>
                  <mi>b</mi>
                  {sub("t", "i")}
                  <mo>−</mo>
                  <mi>a</mi>
                  {pow(sub("t", "i"), "2")}
                  <mo>)</mo>
                </mrow>,
                "2",
              )}
            </mrow>
          </Formula>
          <p>
            The parabola is curved in time but linear in its coefficients: a simple quadratic curve{" "}
            <Quote id="nist-linear-ls" /> (<Cite id="nist-linear-ls" />). So <M><mi>S</mi></M> is a bowl in the three
            coefficients, and at its bottom its three partial derivatives are zero. Setting them to zero gives three
            linear equations, the normal equations (<Cite id="nist-ls" />). With time measured from the middle of the
            window, <M>
              <mi>u</mi>
              <mo>=</mo>
              <mi>t</mi>
              <mo>−</mo>
              <mover>
                <mi>t</mi>
                <mo>¯</mo>
              </mover>
            </M>
            , they read:
          </p>
          <Formula label="The normal equations of the parabola in centred time">
            <mtable>
              {[0, 1, 2].map((row) => (
                <mtr key={row}>
                  <mtd>
                    <mrow>
                      {sumU(row)}
                      <mi>c</mi>
                      <mo>+</mo>
                      {sumU(row + 1)}
                      <mi>b</mi>
                      <mo>+</mo>
                      {sumU(row + 2)}
                      <mi>a</mi>
                      <mo>=</mo>
                      <mo>∑</mo>
                      {row === 0 ? null : row === 1 ? <mi>u</mi> : pow(<mi>u</mi>, "2")}
                      <mi>z</mi>
                    </mrow>
                  </mtd>
                </mtr>
              ))}
            </mtable>
          </Formula>
          <p>
            Centring leaves <M><mi>a</mi></M> alone and keeps the numbers small. On a window symmetric about its middle
            sample, as every window in this lesson is, it does more: the odd sums of <M><mi>u</mi></M> are zero, the
            equation for <M><mi>a</mi></M> comes apart from the one for <M><mi>b</mi></M>, and what is left has a
            closed form:
          </p>
          <Formula label="The closed form of the quadratic coefficient on a symmetric window">
            <mrow>
              <mi>a</mi>
              <mo>=</mo>
              <mfrac>
                <mrow>
                  {sum()}
                  {sub("w", "i")}
                  {sub("z", "i")}
                </mrow>
                <mrow>
                  {sum()}
                  {pow(sub("w", "i"), "2")}
                </mrow>
              </mfrac>
              <mo>,</mo>
              <mspace width="1em" />
              {sub("w", "i")}
              <mo>=</mo>
              {pow(sub("u", "i"), "2")}
              <mo>−</mo>
              <mi>m</mi>
            </mrow>
          </Formula>
          <p>
            Here <M><mi>m</mi></M> is the mean of the squared times. The weights are positive at both ends of the
            window, negative in the middle, and add up to zero, so the estimate compares the height at the ends with
            the height in the middle and nothing else: lift every sample by the same amount and it does not move. That
            line is the estimator behind the gravity check on <a href="/quality">/quality</a>, and the query at the end
            of this page computes it in SQL.
          </p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">One shot</h2>
          <p>
            Start with the shot <a href="/quality">/quality</a> replays, which nobody picked by eye: of every flight the
            check accepted in its calibration matches, it is the one whose g sits closest to their median. It is shot {q("hook.shot_id")} of match {q("hook.match_id")}: {l("samples")} heights, one per
            frame, from {l("half_s")}&nbsp;s before the highest one to {l("half_s")}&nbsp;s after it.
          </p>
          <FitPlot hook={GRAVITY_HOOK} />
          <p>
            The least-squares parabola gives g = {l("fit_g")}&nbsp;m/s², {l("fit_below_pct")}&nbsp;% below {G}. The check itself
            published {q("hook.g_data")}. The two differ because the file stores each height to a tenth of a
            millimetre, and rounding of that size can move g by {l("rounding_bound")}&nbsp;m/s² at most.
          </p>
          <p>
            The fit is tight: a residual root mean square of {l("fit_rms_mm")}&nbsp;mm, the largest {l("fit_max_mm")}&nbsp;mm.
            Now hold g at {G} and let the other two coefficients do the best they can: the RMS
            rises to {l("g_rms_mm")}&nbsp;mm, about {l("rms_ratio")} times as much. At standard
            gravity the parabola bends too hard for this flight, so the residuals climb at both ends and sink in the
            middle. The data do not merely tolerate a lower g. They ask for it.
          </p>
          <p>
            The residuals at the least-squares g are not a random scatter either: neighbouring samples tend to fall on
            the same side of zero. This lesson shows the pattern and does not read it; one flight is not enough to say
            what it is.
          </p>
        </section>

        <section aria-labelledby="matches-h">
          <h2 id="matches-h">From one shot to every match</h2>
          <p>
            One flight could be a fluke. The check ran the same fit over every shot of the bundle&apos;s{" "}
            {q("summary.basketball_matches")} matches that gave a clean window, with no block, no bounce off the rim
            after the peak and a small residual. Each row is one match: the median g of its accepted flights, the
            quartiles around it and how many there were.
          </p>
          <PerMatch matches={GRAVITY_MATCHES} g={GRAVITY_HOOK.g_real} />
          <p>
            Two things stand out. Every median is below {G}: {l("medians_below")} of {l("sign_n")}. So is every upper
            quartile, the value three quarters of a match&apos;s flights fall under: {l("q3_below")} of{" "}
            {l("matches")}. This is not a handful of odd shots dragging an average down. Most flights in every match
            curve less than gravity says they should.
          </p>
          <p>
            How likely is that by chance? The sign test needs no assumption about how g is spread within a match. If
            nothing pushed the medians one way, each would land above or below the reference like a fair coin:{" "}
            <Quote id="webb-sign-test" /> (<Cite id="webb-sign-test" />). The chance that all <M><mi>n</mi></M> land
            below is
          </p>
          <Formula label="The one-sided sign test when every value falls below the reference">
            <mrow>
              <mi>p</mi>
              <mo>=</mo>
              <msup>
                <mn>2</mn>
                <mrow>
                  <mo>−</mo>
                  <mi>n</mi>
                </mrow>
              </msup>
            </mrow>
          </Formula>
          <p>which for these matches is {l("sign_p")}.</p>
          <p>
            The matches split in two, and the split matters. The check&apos;s thresholds were fixed on{" "}
            {q("summary.basketball_calibration_matches")} calibration matches; the other{" "}
            {q("summary.basketball_control_matches")} were scored afterwards with those thresholds frozen. If the low g
            came from tuning, the control matches would give it away. They do not: the calibration medians span{" "}
            {q("summary.ranges.gravity_g_calibration")}&nbsp;m/s² and the control medians{" "}
            {q("summary.ranges.gravity_g_control")}.
          </p>
          <p>
            A similar check on the football bundle gives {q("summary.ranges.gravity_g_football")}&nbsp;m/s², published as a
            number only: its ball height is marked <code>unverified</code> in <code>z_ball_status</code>, with no
            calibration reference to grade it against.
          </p>
        </section>

        <section aria-labelledby="not-h">
          <h2 id="not-h">What does not explain it</h2>
          <p>
            A gravity that comes out low has many candidate causes. The check&apos;s own thresholds are out already:
            the control matches settled that. A few more can be tested here, with the shot above, synthetic flights
            whose g is known, and arithmetic on what /quality publishes.
          </p>

          <h3>Random noise</h3>
          <p>
            Every tracked height carries some error. But the estimate is a weighted sum of heights, so errors with zero
            mean widen the spread of g and leave its average where it was. For independent noise of standard deviation{" "}
            <M><mi>σ</mi></M> on every sample, the spread is
          </p>
          <Formula label="The standard deviation of g under independent noise">
            <mrow>
              <mi>sd</mi>
              <mo>(</mo>
              <mi>g</mi>
              <mo>)</mo>
              <mo>=</mo>
              <mfrac>
                <mrow>
                  <mn>2</mn>
                  <mi>σ</mi>
                </mrow>
                <msqrt>
                  {sum()}
                  {pow(sub("w", "i"), "2")}
                </msqrt>
              </mfrac>
            </mrow>
          </Formula>
          <p>
            For this window, noise of {l("noise_sigma_mm")}&nbsp;mm gives an sd of {l("sd_at_sigma")}&nbsp;m/s². Even if the
            whole residual of the fit, {l("fit_rms_mm")}&nbsp;mm, were noise of that kind, the sd would be {l("sd_at_rms")}{" "}
            and the shot&apos;s g would sit about {l("gap_sd")} of them from {G}. The figure tries it: the shot redrawn
            at standard gravity, noise on every height, fitted again.
          </p>
          <NoiseStrip hook={GRAVITY_HOOK} />
          <p>
            However much noise you add, the cloud stays centred where it started. Noise does not turn {G} into{" "}
            {l("fit_g")}, and across matches it would scatter the medians on both sides of the reference, not put them
            all on one.
          </p>

          <h3>The window</h3>
          <p>
            The check fits {l("window_h_p3")} samples on each side of the highest one, and any window is a trade. A
            short one is less exposed to whatever bends the ends of a flight, but its g is far noisier; a long one is
            steadier and leans on the ends. If the low g came from the window, some size of it should bring g back.
          </p>
          <WindowPlot hook={GRAVITY_HOOK} />
          <p>
            None does. On this shot the highest g at any half-window is {l("window_g_max")}&nbsp;m/s², at{" "}
            <var>H</var> = {l("window_h_at_max")}. The shortest windows swing widely, down to{" "}
            {l("window_g_shortest")} at <var>H</var> = {l("window_h_shortest")}, with error bars to match.
          </p>

          <h3>A linear smoother</h3>
          <p>
            Trackers smooth. Suppose each reported height were a weighted average of nearby heights of the flight, with
            the same weights at every frame and weights that sum to one. Feed it a parabola:
          </p>
          <Formula label="A linear smoother with weights that sum to one">
            <mrow>
              <mi>s</mi>
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <mo>=</mo>
              {sum("k")}
              {sub("h", "k")}
              <mi>z</mi>
              <mo>(</mo>
              <mi>t</mi>
              <mo>−</mo>
              <mi>k</mi>
              <mi>Δ</mi>
              <mo>)</mo>
              <mo>,</mo>
              <mspace width="1em" />
              {sum("k")}
              {sub("h", "k")}
              <mo>=</mo>
              <mn>1</mn>
            </mrow>
          </Formula>
          <p>
            Expand each term and the coefficient of <M>{pow(<mi>t</mi>, "2")}</M> comes out as <M><mi>a</mi></M> times
            the sum of the weights, which is one. Such a smoother can quiet the noise, delay the flight or lift it, but
            not flatten its curve. The check&apos;s own synthetic test agrees: a parabola at standard gravity, smoothed
            by a centred moving average of {l("moving_average_k")} samples, gives back g = {l("moving_average_g")}. The
            argument holds well inside a long track; it says nothing about a filter&apos;s first frames, next to the
            hand.
          </p>

          <h3>A lower measuring rate</h3>
          <p>
            Another way to bend a flight is to measure it less often and fill in between. That is still linear in the
            heights, but it does not act the same at every frame: a sample on a knot is kept and the ones between are
            replaced. In the check&apos;s synthetic flight, true only on one frame in {l("knot_every")} and linearly
            interpolated in between, g moves from {l("knots_down_pct")}&nbsp;% down to {l("knots_up_pct")}&nbsp;% up, depending
            on where the knots fall. That is small and goes both ways, against a gap of {l("fit_below_pct")}&nbsp;%. It is a
            synthetic result; the lesson does not ask whether the files were built this way.
          </p>

          <h3>The clock and the ruler</h3>
          <p>
            g is a length over a time squared, so a file whose seconds or metres were off would move it. For this shot to fall at {G}, every time in the file would have to shrink by{" "}
            {l("time_shrink_pct")}&nbsp;%. Or every height would have to be divided by {l("height_scale")}; that is, the file
            would be reporting heights {l("fit_below_pct")}&nbsp;% short. The files cannot settle either. Both clocks in a frame,
            the video clock and the game clock, come from the provider; the frame clock steps exactly in{" "}
            {q("summary.ranges.clock_step_exact_basketball")}&nbsp;% of frames, which shows it is regular, not that its
            second is a second. Nothing in the files gives an outside height either.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            Anything computed from the ball&apos;s height in flight depends on it. Release speed and angle, hang time,
            the height of the arc and the angle at the rim all depend on the same heights. The entry-angle check on
            /quality shows it: the angle the bundle&apos;s own curve gives at the rim sits{" "}
            {q("summary.ranges.entry_angle_gap")}&nbsp;degrees, median per match, from the angle the geometry of the same
            shot requires. The <a href="/bulletin">bulletin</a> tells a consumer to expect a systematic offset of this
            size, not random error.
          </p>
          <p>
            Beyond basketball, the idea applies wherever physics fixes a parameter: fitting it is a check that needs
            no ground truth, and the residuals say how firmly the data disagree. A per-match g belongs next to anything
            derived from the ball&apos;s height, the way a calibration certificate sits next to an instrument.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              Every height here is the provider&apos;s model of where the ball was. In the basketball bundle the ball is
              flagged as detected in {q("summary.ranges.detection_ball_pct_basketball")}&nbsp;% of rows, and the
              provider&apos;s dictionary defines the flag for the ball as <Quote id="skillcorner-tracking" /> (
              <Cite id="skillcorner-tracking" />).
            </li>
            <li>There is no outside clock and no outside ruler, so the time scale and the height scale stay untested.</li>
            <li>The model has no air. Drag and spin are left out of the parabola, and this lesson does not size them.</li>
            <li>
              The shot&apos;s heights are rounded to a tenth of a millimetre, which can move the refit here by up to{" "}
              {l("rounding_bound")}&nbsp;m/s².
            </li>
            <li>Football appears only as its published range, with its ball height unverified.</li>
            <li>The cause stays open. The lesson shows what does not explain the figure, not what does.</li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>
              Drag the g in the first figure from the least-squares value to standard gravity and watch the residual
              bars. Where do they grow first, and why there?
            </li>
            <li>
              Take the half-window down to its smallest and back up. Which sizes would you defend, and why?
            </li>
            <li>Add noise at the largest sd, again and again. Does the mean of the cloud ever approach the shot&apos;s g?</li>
            <li>
              With pencil and paper, smooth a parabola with weights that sum to one and check that the squared term
              keeps its coefficient. Then break the rule.
            </li>
            <li>
              Run the query below on another match: change the id in both file names and compare the result with that
              match&apos;s row in the table.
            </li>
          </ul>
        </section>

        <Reproduce sql={sql}>
          <p>
            The query is the check&apos;s basketball fit in DuckDB, written for the two public files of match{" "}
            {q("hook.match_id")}. It needs nothing else: no Track Lab code and no intermediate tables.
          </p>
          <ol>
            <li>
              Clone <code>https://github.com/SkillCorner/opendata-basketball</code> with Git LFS, which holds the
              tracking files, and check out <code>4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66</code>.
            </li>
            <li>
              Open a terminal in <code>data/matches/114086</code>, next to <code>114086_tracking_data.jsonl.gz</code> and{" "}
              <code>114086_dynamic_events.json</code>.
            </li>
            <li>
              Save the query as <code>gravity.sql</code> and run <code>duckdb &lt; gravity.sql</code>.
            </li>
          </ol>
          <p>
            It returns {q("checks.gravity.bb:114086.flights")} flights and a median g of{" "}
            {q("checks.gravity.bb:114086.g_median")}, that match&apos;s row in the table above. The same query, with
            only the id changed, gives every row of it; it was checked that way with DuckDB <code>1.5.5</code>.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="nist-linear-ls" full /> and <Cite id="nist-ls" full />: least squares, and why a quadratic counts as a
              linear model.
            </li>
            <li>
              <Cite id="webb-sign-test" full />: the sign test, step by step.
            </li>
            <li>
              <Cite id="cgpm-1901" full /> and <Cite id="codata-gn" full />: where the standard value comes from.
            </li>
            <li>
              <Cite id="skillcorner-tracking" full />: the provider&apos;s definitions of every field in the tracking files.
            </li>
            <li>
              <a href="/quality">/quality</a> and the <a href="/bulletin">bulletin</a>: the check this lesson unpacks,
              beside the other checks of the bundles.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures hook={GRAVITY_HOOK} matches={GRAVITY_MATCHES} />
    </main>
  );
}
