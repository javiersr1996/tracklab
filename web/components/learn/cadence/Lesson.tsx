import type { ReactNode } from "react";
import { CLIPS, column, FAST_ROWS, HOOKS, POSE, publishedFigure } from "../../../lib/learn/cadence-data";
import { cadenceFigures } from "../../../lib/learn/cadence-figures";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { ExposeFigures } from "./ExposeFigures";
import { LagPlot } from "./LagPlot";
import { NoiseCloud } from "./NoiseCloud";
import { PerPlayer } from "./PerPlayer";

// Lesson 5. No figure is typed: `f(name)` prints a value of a published file, named
// "<file under public/data>:<dotted path>", and `l(key)` one of `cadenceFigures`, each as a
// `data-fig` the e2e compares with its source.
const F = cadenceFigures(HOOKS, FAST_ROWS);
const get = (root: unknown, path: string): unknown =>
  path.split(".").reduce<unknown>((at, key) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[key] : undefined), root);
const l = (key: string) => <Fig name={`learn.${key}`}>{String(get(F, key))}</Fig>;
const f = (name: string) => <Fig name={name}>{String(publishedFigure(name))}</Fig>;
const p = (path: string) => f(`pose.json:${path}`);

const [A, B] = HOOKS;
const ca = (path: string) => f(`${A.file}:${path}`);
const cb = (path: string) => f(`${B.file}:${path}`);
const la = (key: string) => l(`hook.${A.match_id}.${key}`);
const lb = (key: string) => l(`hook.${B.match_id}.${key}`);
const playerA = CLIPS[A.file].windows?.[0].player ?? -1;
const playerB = CLIPS[B.file].windows?.[0].player ?? -1;
const rowA = (() => {
  const row = FAST_ROWS[String(A.match_id)].find((r) => r.team_id === A.team_id && r.number === A.number);
  if (!row) throw new Error("the hook player of the first clip has no fast-band row in pose.json");
  return row;
})();
const cell = (match: number, row: number, name: string) => p(`tables.matches.${match}.${row}.${column(name)}`);
const COLUMNS = {
  team_id: column("team_id"),
  number: column("number"),
  finite_s: column("finite_s"),
  cad_s_p50_hz: column("cad_s_p50_hz"),
  cad_s_sd_hz: column("cad_s_sd_hz"),
};
const DETECTED_ONLY = POSE.limits.find((x) => x.id === "detected_only")?.text ?? "";

const sub = (x: string, i: string) => (
  <msub>
    <mi>{x}</mi>
    <mi>{i}</mi>
  </msub>
);
const pow = (base: ReactNode, n: string) => (
  <msup>
    {base}
    <mn>{n}</mn>
  </msup>
);
const centred = (i: ReactNode) => (
  <mrow>
    <mo>(</mo>
    {i}
    <mo>−</mo>
    <mover>
      <mi>s</mi>
      <mo>¯</mo>
    </mover>
    <mo>)</mo>
  </mrow>
);

function PerMatchText({ match }: { match: string }) {
  const m = (key: string) => l(`match.${match}.${key}`);
  return (
    <>
      In match {p(`protocol.${match === String(POSE.protocol.calibration) ? "calibration" : "confirmation"}`)}, {m("players")} players
      have at least {p("protocol.numbers.min_windows")} fast-band windows with a cadence, {m("windows")} windows between them.
      Their cadences run from {m("cadence_min")} to {m("cadence_max")} steps/s; their sds from {m("sd_min")} to{" "}
      {m("sd_max")}, with a median of {m("sd_median")}.
    </>
  );
}

export function Lesson({ script }: { script: string }) {
  return (
    <main className="page lesson learn-cadence">
      <LessonHead
        n={5}
        title="How many steps per second?"
        level="Advanced"
        result={[
          { label: "Cadence of the first clip's runner", values: [Number(publishedFigure(`${A.file}:windows.0.cadence_hz`))], unit: "steps/s" },
          { label: "Its sd from the predicted error", values: [Number(publishedFigure(`${A.file}:windows.0.cadence_sd_hz`))], unit: "steps/s" },
        ]}
      >
        <p className="lede">
          SkillCorner&apos;s open body pose places {ca("joints.length")} joints on a player {ca("fps")} times a second, each
          with its own predicted error. Two of them, the ankles, are enough to count a runner&apos;s steps. This lesson reads
          that count from a repeating signal and works out how far the error lets it move.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            Cadence is the number of steps a runner takes per second. On <a href="/tracking/pose">/tracking/pose</a> Track Lab publishes one
            for every player of two football matches, in the fast band from {p("protocol.bands.high_m_s_from")}&nbsp;m/s, with
            an sd beside each. This lesson takes that number apart. It asks two things that any reading of a repeating signal
            has to answer: how do you find the period of a signal only a few cycles long, and how sure can you be of it when
            every sample carries a known error?
          </p>
          <p>
            The second question can be answered only because the provider says how wrong each joint may be:{" "}
            <Quote id="skillcorner-bodypose" /> (<Cite id="skillcorner-bodypose" />). Without that, an sd would have to come
            from repeating the measurement, and nobody can make a player run the same two seconds twice.
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">A period from the autocorrelation</h2>
          <p>
            Start with a signal that repeats once per stride. Take the left ankle minus the right ankle, both in the same
            frame, and project the difference onto the direction the player is moving:
          </p>
          <Formula label="The ankles' separation along the direction of travel">
            <mrow>
              <mi>s</mi>
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <mo>=</mo>
              <mo>(</mo>
              {sub("p", "L")}
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <mo>−</mo>
              {sub("p", "R")}
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <mo>)</mo>
              <mo>·</mo>
              <mover>
                <mi>d</mi>
                <mo>^</mo>
              </mover>
            </mrow>
          </Formula>
          <p>
            Here <M><mover><mi>d</mi><mo>^</mo></mover></M> is the unit vector of the player&apos;s net displacement over the
            window. Because <M><mi>s</mi></M> is a difference between two joints of the same body in the same frame, where
            the body stands on the pitch drops out. While the left foot is ahead <M><mi>s</mi></M> is positive, while the right
            is ahead it is negative: it swings once per stride, and a stride is two steps.
          </p>
          <p>
            To find how long one swing lasts, compare the signal with itself moved later in time. The autocorrelation at lag{" "}
            <M><mi>k</mi></M> multiplies each centred sample by the one <M><mi>k</mi></M> frames on and averages the{" "}
            <M><mi>n</mi><mo>−</mo><mi>k</mi></M> products a window of <M><mi>n</mi></M> samples has at that lag:
          </p>
          <Formula label="The autocorrelation at lag k, averaged over its own products">
            <mrow>
              <mi>r</mi>
              <mo>(</mo>
              <mi>k</mi>
              <mo>)</mo>
              <mo>=</mo>
              <mfrac>
                <mn>1</mn>
                <mrow>
                  <mi>n</mi>
                  <mo>−</mo>
                  <mi>k</mi>
                </mrow>
              </mfrac>
              <msub>
                <mo>∑</mo>
                <mi>i</mi>
              </msub>
              {centred(sub("s", "i"))}
              {centred(
                <msub>
                  <mi>s</mi>
                  <mrow>
                    <mi>i</mi>
                    <mo>+</mo>
                    <mi>k</mi>
                  </mrow>
                </msub>,
              )}
            </mrow>
          </Formula>
          <p>
            At lag zero this is the variance. Move the copy by half a stride and the feet are swapped, so the products turn
            negative; move it by a whole stride and the signal lies on itself again, so <M><mi>r</mi></M> climbs back. The
            lag of the first peak after <M><mi>r</mi></M> has gone negative is the stride, in frames. NIST&apos;s handbook
            divides every lag by <M><mi>n</mi></M>; that shrinks the late lags more than the early ones and drags a peak
            towards shorter lags, so the pipeline averages each lag over its own <M><mi>n</mi><mo>−</mo><mi>k</mi></M>{" "}
            products.
          </p>
          <p>
            A peak can also be luck. The handbook states the test for that plainly: <Quote id="nist-autocorrelation" /> (
            <Cite id="nist-autocorrelation" />). It gives the band they stay in as a normal quantile over the square root of
            the sample size. The pipeline puts the number of products there, so the band widens with the lag,
            and a first peak inside it gives no cadence at all rather than a later, luckier one:
          </p>
          <Formula label="A peak counts only above white noise's band">
            <mrow>
              <mfrac>
                <mrow>
                  <mi>r</mi>
                  <mo>(</mo>
                  <mi>k</mi>
                  <mo>)</mo>
                </mrow>
                <mrow>
                  <mi>r</mi>
                  <mo>(</mo>
                  <mn>0</mn>
                  <mo>)</mo>
                </mrow>
              </mfrac>
              <mo>&gt;</mo>
              <mfrac>
                <mi>z</mi>
                <msqrt>
                  <mi>n</mi>
                  <mo>−</mo>
                  <mi>k</mi>
                </msqrt>
              </mfrac>
            </mrow>
          </Formula>
          <p>
            with <M><mi>z</mi></M> = {l("band_z")}, the pipeline&apos;s two-sided normal quantile. A lag counted in whole
            frames is coarse: at {ca("fps")} frames a second, a peak at lag {la("peak_k")} means {la("cadence_k")} steps/s
            and one frame more means {la("cadence_k_next")}. The pipeline refines the lag with the parabola through the peak
            and its two neighbours, which works for any peak smooth at the top, since{" "}
            <Quote id="smith-parabola" /> (<Cite id="smith-parabola" />). The vertex sits a fraction{" "}
            <M><mi>δ</mi></M> of a frame from <M><mi>k</mi></M>:
          </p>
          <Formula label="The parabola's vertex and the cadence it gives">
            <mrow>
              <mi>δ</mi>
              <mo>=</mo>
              <mfrac>
                <mrow>
                  <mi>r</mi>
                  <mo>(</mo>
                  <mi>k</mi>
                  <mo>−</mo>
                  <mn>1</mn>
                  <mo>)</mo>
                  <mo>−</mo>
                  <mi>r</mi>
                  <mo>(</mo>
                  <mi>k</mi>
                  <mo>+</mo>
                  <mn>1</mn>
                  <mo>)</mo>
                </mrow>
                <mrow>
                  <mn>2</mn>
                  <mo>(</mo>
                  <mi>r</mi>
                  <mo>(</mo>
                  <mi>k</mi>
                  <mo>−</mo>
                  <mn>1</mn>
                  <mo>)</mo>
                  <mo>−</mo>
                  <mn>2</mn>
                  <mi>r</mi>
                  <mo>(</mo>
                  <mi>k</mi>
                  <mo>)</mo>
                  <mo>+</mo>
                  <mi>r</mi>
                  <mo>(</mo>
                  <mi>k</mi>
                  <mo>+</mo>
                  <mn>1</mn>
                  <mo>)</mo>
                  <mo>)</mo>
                </mrow>
              </mfrac>
              <mo>,</mo>
              <mspace width="1em" />
              <mi>c</mi>
              <mo>=</mo>
              <mfrac>
                <mrow>
                  <mn>2</mn>
                  <mi>f</mi>
                </mrow>
                <mrow>
                  <mi>k</mi>
                  <mo>+</mo>
                  <mi>δ</mi>
                </mrow>
              </mfrac>
            </mrow>
          </Formula>
          <p>
            with <M><mi>f</mi></M> the frame rate; the factor two turns strides into steps. A spectrum asks the same question
            from the other side, and its fundamental is where the periodogram peaks. On a window of {p("protocol.width")}{" "}
            frames, though, its bins sit {l("bin_hz")}&nbsp;Hz apart in <M><mi>s</mi></M>, {l("bin_steps")}&nbsp;step/s in
            cadence: coarser still than whole lags. Either can be refined with a parabola; the pipeline refines the lag.
          </p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">One window</h2>
          <p>
            The clip /tracking/pose replays for match {ca("match_id")} holds one window chosen by rule, not by eye: of every
            fast-band window in the match, the one whose cadence sits nearest the match&apos;s median, never the fastest. It
            belongs to number {ca(`players.${playerA}.number`)} of team {ca(`players.${playerA}.team_id`)}, running at{" "}
            {ca("windows.0.speed_m_s")}&nbsp;m/s, and spans {la("samples")} frames, {la("seconds")}&nbsp;s.
          </p>
          <LagPlot hook={A} />
          <p>
            <M><mi>r</mi></M> first turns negative at lag {la("first_negative")} and comes back to a peak at lag{" "}
            {la("peak_k")}, where it holds {la("peak_ratio")} of its value at zero against a band of {la("peak_band")}: well
            clear of noise. The parabola moves the peak by {la("peak_shift")} of a frame, to a stride of {la("stride_s")}
            &nbsp;s and a cadence of {la("cadence")} steps/s. The pipeline published {ca("windows.0.cadence_hz")} for the
            same window; the small gap is the clip&apos;s <M><mi>s</mi></M>, written to the millimetre, against the
            unrounded joints the pipeline read.
          </p>
        </section>

        <section aria-labelledby="error-h">
          <h2 id="error-h">Carrying the error through</h2>
          <p>
            The pipeline reads each ankle&apos;s predicted error as the sd of an independent normal error on each axis, a
            conservative reading of a percentile. <M><mi>s</mi></M> is a difference of two ankles along a unit vector, so
            that first step is exact: the variances add.
          </p>
          <Formula label="The variance of s in one frame from the two ankles' predicted errors">
            <mrow>
              {pow(sub("σ", "i"), "2")}
              <mo>=</mo>
              {pow(
                <msub>
                  <mi>e</mi>
                  <mrow>
                    <mi>L</mi>
                    <mo>,</mo>
                    <mi>i</mi>
                  </mrow>
                </msub>,
                "2",
              )}
              <mo>+</mo>
              {pow(
                <msub>
                  <mi>e</mi>
                  <mrow>
                    <mi>R</mi>
                    <mo>,</mo>
                    <mi>i</mi>
                  </mrow>
                </msub>,
                "2",
              )}
            </mrow>
          </Formula>
          <p>
            In this window <M><mi>σ</mi></M> is {la("sigma_median_mm")}&nbsp;mm in the median frame and{" "}
            {la("sigma_max_mm")}&nbsp;mm at most, against a swing of {la("amplitude_mm")}&nbsp;mm either side of zero.
          </p>
          <p>
            The next step is not linear: the cadence comes out of a peak search and a parabola. There are two standard ways to
            carry an error through a step like that. The first is the propagation of error formula, which NIST&apos;s handbook
            introduces this way: <Quote id="nist-propagation" /> (<Cite id="nist-propagation" />). To first order, a small change in each sample
            moves the cadence in proportion to the derivative there, and independent changes add in quadrature:
          </p>
          <Formula label="The first-order sd of the cadence">
            <mrow>
              <mi>sd</mi>
              <mo>(</mo>
              <mi>c</mi>
              <mo>)</mo>
              <mo>≈</mo>
              <msqrt>
                <msub>
                  <mo>∑</mo>
                  <mi>i</mi>
                </msub>
                {pow(
                  <mrow>
                    <mo>(</mo>
                    <mfrac>
                      <mrow>
                        <mo>∂</mo>
                        <mi>c</mi>
                      </mrow>
                      <mrow>
                        <mo>∂</mo>
                        {sub("s", "i")}
                      </mrow>
                    </mfrac>
                    <mo>)</mo>
                  </mrow>,
                  "2",
                )}
                {pow(sub("σ", "i"), "2")}
              </msqrt>
            </mrow>
          </Formula>
          <p>
            The derivatives can be taken numerically, nudging one sample at a time. Here the formula gives{" "}
            {la("linear_sd")} steps/s.
          </p>
          <p>
            The second is Monte Carlo: draw a normal error for every sample, read the cadence again, repeat, and take the sd
            of what comes out. It needs no derivative, and it is the one to trust when, in the words of the supplement to the
            GUM, <Quote id="jcgm-101" /> (<Cite id="jcgm-101" />). With {l("draws")} draws, as many as the pipeline takes, from one stream seeded
            with its base seed, {l("seed")}, the sd here is {la("mc_sd")}, {la("full_ratio")} times the first-order one. The
            pipeline&apos;s draws, on the unrounded joints, gave {ca("windows.0.cadence_sd_hz")}.
          </p>
          <NoiseCloud hook={A} />
          <p>
            The two methods agree when the noise is small: at {l("scale_low")} of the predicted error the Monte Carlo sd is{" "}
            {la("low_ratio")} times the first-order one. At {l("scale_high")} times the error it is {la("high_ratio")} times
            as large, and {la("high_unresolved")} of {l("draws")} copies no longer have a cadence at all. A peak search is
            smooth only close to the signal it started from, and the provider&apos;s error is already large enough to leave
            that neighbourhood.
          </p>
        </section>

        <section aria-labelledby="players-h">
          <h2 id="players-h">From one window to every player</h2>
          <p>
            The other published clip, from match {cb("match_id")}, holds number {cb(`players.${playerB}.number`)} of team{" "}
            {cb(`players.${playerB}.team_id`)} at {cb("windows.0.speed_m_s")}&nbsp;m/s, picked by the same rule. Both windows
            read the same way:
          </p>
          <div className="table-scroll">
            <table className="learn-cadence-table">
              <thead>
                <tr>
                  <th scope="col">match</th>
                  <th scope="col">cadence here</th>
                  <th scope="col">published</th>
                  <th scope="col">first-order sd</th>
                  <th scope="col">Monte Carlo sd</th>
                  <th scope="col">published sd</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { h: A, c: ca, w: la },
                  { h: B, c: cb, w: lb },
                ].map(({ h, c, w }) => (
                  <tr key={h.match_id}>
                    <td>{c("match_id")}</td>
                    <td>{w("cadence")}</td>
                    <td>{c("windows.0.cadence_hz")}</td>
                    <td>{w("linear_sd")}</td>
                    <td>{w("mc_sd")}</td>
                    <td>{c("windows.0.cadence_sd_hz")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            The number /tracking/pose prints for a player is not one window but the median over all of that player&apos;s fast-band windows, and its
            sd comes from the same draws carried through the median. Many windows pull it down: for the player above, the
            median of {cell(A.match_id, rowA.row, "finite_s")} windows carries {cell(A.match_id, rowA.row, "cad_s_sd_hz")}, against{" "}
            {ca("windows.0.cadence_sd_hz")} for the one window.
          </p>
          <PerPlayer rows={FAST_ROWS} columns={COLUMNS} />
          <p>
            <PerMatchText match={String(A.match_id)} /> <PerMatchText match={String(B.match_id)} />
          </p>
          <p>
            In both matches the spread between players is many times the error any one of them carries, so the error
            the joints carry does not hide the difference between players. That is the sd of the joints&apos; predicted error
            only, not the variation of one player between windows (see Limitations). It does not say why they differ, and this lesson does not ask. /tracking/pose shows the
            rule the protocol froze around this comparison before the second match was read, and how that match met it.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            Every number derived from body pose inherits the error of the joints it reads. A cadence printed without its sd
            invites a reader to compare two players whose difference sits inside the noise; printed with it, the comparison
            carries its own scale. The first-order formula is cheap and often enough, but it is a linearisation, and this
            window shows where it gives way: at the provider&apos;s own error it would report a cadence more certain than it
            is.
          </p>
          <p>
            The same steps work elsewhere. Anything that repeats, a stride, an arm swing, a bounce of the ball, can be read from the
            first peak of its autocorrelation, checked against the white-noise band and refined with a parabola. Anything
            computed from inputs with a stated error can carry that error forward by Monte Carlo when the formula is not to
            be trusted, and the formula itself says, by how far it falls short, how nonlinear the step was.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              Body pose exists only where the provider found the player: <q>{DETECTED_ONLY}</q> (
              <Cite id="skillcorner-bodypose" />). Every window here lies in frames with a skeleton; that is a stated
              assumption, and the lesson does not ask what it leaves out.
            </li>
            <li>
              The predicted error is a percentile of an absolute error, read as an sd. Ankles, axes and frames are taken as
              independent; that is not tested, and errors that move together would change the sd by an amount this lesson
              does not size.
            </li>
            <li>
              The direction of travel comes from the player&apos;s x and y in the pose file, which carry no predicted error,
              so none is carried through them.
            </li>
            <li>
              The sd is the part of the error the joints&apos; predicted error explains. It is not the spread of a
              player&apos;s cadence from window to window, which also holds whatever changed in the running itself.
            </li>
            <li>
              If the provider called the forward foot the left one in every frame, <M><mi>s</mi></M> would swing once per
              step and every cadence would double. The protocol could not rule that out; /tracking/pose lists it with its other blind
              spot.
            </li>
            <li>Two matches, one window per published clip, and the fast band only.</li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>
              In the first figure, drag the lag from zero to the first peak and watch the white copy. At which lag are the
              feet exactly swapped, and what does the autocorrelation do there?
            </li>
            <li>Jump to the first peak, then read the lags either side. How far would the cadence move without the parabola?</li>
            <li>
              In the second figure, add copies at the smallest error, then switch to the largest. When does the cloud stop
              being symmetric about the window&apos;s own cadence?
            </li>
            <li>In the third figure, find the players with the most and the fewest windows. Does the sd follow the count?</li>
            <li>Run the script below on the other clip, then change its seed. Which digits of the sd move?</li>
          </ul>
        </section>

        <Reproduce sql={script} browser="cadence">
          <p>
            The script reads the clip /tracking/pose already publishes and needs nothing but Python&apos;s standard library: no Track
            Lab code, no numpy, and the provider&apos;s match files only through the clip.
          </p>
          <ol>
            <li>
              Save it as <code>cadence.py</code>.
            </li>
            <li>
              Run <code>python cadence.py</code>. It downloads{" "}
              <code>https://tracklab-sable.vercel.app/data/pose/hook_1925299.json</code>, {p("clips.0.bytes")} bytes with
              checksum <code>{p("clips.0.sha256")}</code>. Pass a saved copy of that file, or of the other clip, as its
              argument to work offline.
            </li>
          </ol>
          <p>
            It prints a cadence of {la("repro_cadence")} steps/s and an sd of {la("repro_sd")} over {la("repro_valid")} of{" "}
            {l("draws")} noisy copies. Those are this page&apos;s figures for the same window, because the script builds{" "}
            <M><mi>s</mi></M> from the clip&apos;s joints, written in whole centimetres, and draws its noise from the
            page&apos;s own generator. The pipeline published {ca("windows.0.cadence_hz")} ± {ca("windows.0.cadence_sd_hz")}{" "}
            from the unrounded joints and its own draws.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="nist-autocorrelation" full />: the autocorrelation, its two normalisations and its band.
            </li>
            <li>
              <Cite id="smith-parabola" full />: the parabola through a peak, derived.
            </li>
            <li>
              <Cite id="nist-propagation" full /> and <Cite id="jcgm-101" full />: the propagation of error formula, and when
              to draw instead.
            </li>
            <li>
              <Cite id="skillcorner-bodypose" full />: the provider&apos;s description of the joints, their error and their
              limits.
            </li>
            <li>
              <a href="/tracking/pose">/tracking/pose</a>: the viewer, the protocol and every player&apos;s row this lesson draws.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures hooks={HOOKS} fast={FAST_ROWS} />
    </main>
  );
}
