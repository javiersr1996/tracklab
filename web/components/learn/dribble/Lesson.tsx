import type { ReactNode } from "react";
import { DRIBBLE, TOUCH } from "../../../lib/learn/dribble-data";
import { lessonDribbleFigures, type DribbleLessonFigures } from "../../../lib/learn/dribble-figures";
import { figureAt, matchFig } from "../../../lib/learn/json-figure";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { BounceStrip } from "./BounceStrip";
import { ExposeFigures } from "./ExposeFigures";
import { PerMatch } from "./PerMatch";

// Lesson 9. No figure is typed: `d(path)` prints a value of dribble.json, `l(key)` one of
// `lessonDribbleFigures` and `x(i, key)` one of its example dribbles, each as a `data-fig` the e2e
// compares with its source.
const F = lessonDribbleFigures(DRIBBLE, TOUCH);
type One = DribbleLessonFigures["dribbles"][number];
const l = (key: Exclude<keyof DribbleLessonFigures, "dribbles">) => <Fig name={`learn.${key}`}>{String(F[key])}</Fig>;
const x = (i: number, key: keyof One) => <Fig name={`learn.dribbles.${i}.${key}`}>{String(F.dribbles[i][key])}</Fig>;
const d = (path: string) => <Fig name={`dribble.${path}`}>{String(figureAt(DRIBBLE, "dribble", `dribble.${path}`))}</Fig>;
const REPRO = DRIBBLE.example.match_id;
const m = (field: string) => <Fig name={matchFig("dribble", REPRO, field)}>{String(figureAt(DRIBBLE, "dribble", matchFig("dribble", REPRO, field)))}</Fig>;
const NATIVE = REPRO.replace(/^bb:/, "");

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
    <main id="main" className="page lesson learn-dribble">
      <LessonHead
        n={9}
        title="How many bounces per second?"
        level="Intermediate"
        result={[
          { label: "Bounces per second, per match", values: [F.rate_lo, F.rate_hi] },
          { label: "Median time between two dribbles", values: [F.med_lo, F.med_hi], unit: "s" },
        ]}
      >
        <p className="lede">
          The provider&apos;s events list every dribble with its frame, and the tracking gives the ball&apos;s height at every
          frame: two witnesses of one rhythm. Match by match, the median time between two dribbles of a touch is {l("med_lo")} to{" "}
          {l("med_hi")}&nbsp;s, {l("rate_lo")} to {l("rate_hi")} bounces per second, and in the median dribble of {l("offset_zero")} of the{" "}
          {l("matches")} matches the ball&apos;s lowest point falls on the event&apos;s own frame. Where the two disagree is where the lesson looks.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            SkillCorner&apos;s basketball events have a table of dribbles: <Quote id="skillcorner-dribbles" /> (
            <Cite id="skillcorner-dribbles" />
            ). Each row carries a <code>frame</code>, <Quote id="skillcorner-dribble-frame" /> (<Cite id="skillcorner-dribble-frame" />
            ), and a <code>touchId</code>, the touch it belongs to: <Quote id="skillcorner-touch" /> (<Cite id="skillcorner-touch" />
            ).
          </p>
          <p>
            The tracking, for its part, gives the ball&apos;s height at every frame. A dribble pushes the ball to the floor and
            catches it on the way up, so the height should fall and rise once per dribble. How often does a player bounce the ball,
            and do the two files agree on when?
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">Points in time and a signal</h2>
          <p>
            The events are points in time. Number the dribbles of one touch in order, with dribble <M><mi>j</mi></M> at frame{" "}
            <M>{sub("n", <mi>j</mi>)}</M>; with <M><mi>f</mi></M> frames per second, {d("fps")} here, the interval to the next one
            is
          </p>
          <Formula label="The interval between two consecutive dribbles of a touch">
            <mrow>
              {sub("Δ", <mi>j</mi>)}
              <mo>=</mo>
              {frac(<>{sub("n", <mrow><mi>j</mi><mo>+</mo><mn>1</mn></mrow>)}<mo>−</mo>{sub("n", <mi>j</mi>)}</>, <mi>f</mi>)}
            </mrow>
          </Formula>
          <p>
            Only inside one touch: between two touches the ball goes to someone else, or the player stops and goes again, and the
            gap measures that instead. Bounces per second are one over the interval, and the median interval of many gives a
            typical rate that one odd gap cannot drag far.
          </p>
          <p>
            The height is a signal, <M><mrow><mi>z</mi><mo>(</mo><mi>n</mi><mo>)</mo></mrow></M>. A bounce shows in it as a low
            point, so each event can be checked against it: look at the frames up to <M><mi>R</mi></M> before and after the
            dribble, {d("reach")} here, and find where the height is lowest. The offset of that frame from the event is
          </p>
          <Formula label="The offset from a dribble to the lowest height around it">
            <mrow>
              {sub("k", <mi>j</mi>)}
              <mo>=</mo>
              <msub>
                <mrow>
                  <mi>arg</mi>
                  <mo>⁡</mo>
                  <mi>min</mi>
                </mrow>
                <mrow>
                  <mo>|</mo>
                  <mi>k</mi>
                  <mo>|</mo>
                  <mo>≤</mo>
                  <mi>R</mi>
                </mrow>
              </msub>
              <mi>z</mi>
              <mo>(</mo>
              {sub("n", <mi>j</mi>)}
              <mo>+</mo>
              <mi>k</mi>
              <mo>)</mo>
            </mrow>
          </Formula>
          <p>
            If the two files agree, the offset is zero or close to it. A lowest height on the window&apos;s first or last frame
            means the window holds no low point at all: the height is still falling, or already rising, as far as the window
            reaches. Two consecutive dribbles whose lowest heights fall on the same frame are two events for one low point.
          </p>
          <p>
            The signal has a rhythm of its own, which needs no event at all. The <a href="/learn/cadence">fifth lesson</a> read a
            stride from the autocorrelation of a body&apos;s signal: <Quote id="nist-autocorrelation" /> (
            <Cite id="nist-autocorrelation" />
            ). A height that bounces is far from random, and the first peak of its autocorrelation, after it turns negative, sits
            at its period.
          </p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">One touch</h2>
          <p>
            The figure follows the touch with the most dribbles in a published possession of match {d("example.match_id")}, the one
            the home page shows: {l("ex_n")} dribbles over {l("ex_seconds")}&nbsp;s. In {l("ex_on_frame")} of them the lowest height
            of the window is on the event&apos;s own frame. Dribbles {l("shared_first")} and {l("shared")} are {l("shared_gap_frames")}{" "}
            frames apart, {l("shared_gap_s")}&nbsp;s, and their lowest heights are the same frame, at {l("shared_z")}&nbsp;m: two
            events, one low point. Across the dribbles&apos; windows the height has {l("ex_low_points")} low points for{" "}
            {l("ex_n")} events.
          </p>
          <BounceStrip ex={TOUCH} figures={{ dribbles: F.dribbles, ac_lag: F.ac_lag, ac_k: F.ac_k }} />
          <p>
            The touch&apos;s {l("ex_intervals")} intervals have a median of {l("ex_median_s")}&nbsp;s, {l("ex_rate")} bounces per
            second, and the short gap is one of them. The height from the first dribble to the last is {l("ac_samples")} samples.
            Its autocorrelation first turns negative at lag {l("ac_first_negative")} and peaks next at lag {l("ac_k")}, at{" "}
            {l("ac_ratio")} of its value at zero; with the parabola through the peak and its two neighbours, as in the fifth
            lesson, the period is {l("ac_lag")} frames, {l("ac_period_s")}&nbsp;s, or {l("ac_rate")} bounces per second. The
            events&apos; median counts the short gap as an interval; the height&apos;s period never sees it.
          </p>
          <figure className="learn-fig surface-dark" data-figure="dribbles">
            <div className="table-scroll">
              <table className="learn-matches">
                <thead>
                  <tr>
                    <th scope="col">dribble</th>
                    <th scope="col">time in the touch (s)</th>
                    <th scope="col">gap from the one before (s)</th>
                    <th scope="col">offset to the lowest height (frames)</th>
                    <th scope="col">lowest height (m)</th>
                  </tr>
                </thead>
                <tbody>
                  {F.dribbles.map((row, i) => (
                    <tr key={row.n} data-dribble={i}>
                      <td>{row.n}</td>
                      <td>{x(i, "t_s")}</td>
                      <td>{i === 0 ? "" : x(i, "gap_s")}</td>
                      <td>{x(i, "offset")}</td>
                      <td>{x(i, "low_z")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <figcaption>
              The dribbles of the touch in the figure above, from the provider&apos;s events and the possession&apos;s published
              heights. A negative offset is a lowest height before the event, a positive one after it.
            </figcaption>
          </figure>
        </section>

        <section aria-labelledby="floor-h">
          <h2 id="floor-h">The lowest height is not the floor</h2>
          <p>
            The lowest heights of this touch are {l("ex_low_min")} to {l("ex_low_max")}&nbsp;m, the median {l("ex_low_median")}. The
            provider&apos;s dictionary says the height <Quote id="skillcorner-ball-z" /> (<Cite id="skillcorner-ball-z" />). Over
            ten matches the median lowest height of a dribble is {l("low_lo")} to {l("low_hi")}&nbsp;m. Where the ball&apos;s
            centre is at the instant it meets the floor is not in the file, and this lesson does not say why the lowest frame stays
            so high; the first lesson left its height scale open in the same way.
          </p>
        </section>

        <section aria-labelledby="matches-h">
          <h2 id="matches-h">From one touch to ten matches</h2>
          <p>
            The pipeline read every dribble with a frame, {l("dribbles_all")} in all, and the {l("intervals")} intervals inside a
            touch, {l("intervals_lo")} to {l("intervals_hi")} per match. Each row of the table is one match.
          </p>
          <PerMatch matches={DRIBBLE.matches} />
          <p>
            The median interval is {l("med_lo")} to {l("med_hi")}&nbsp;s, {l("rate_lo")} to {l("rate_hi")} bounces per second; the
            tenth percentile is {l("p10_lo")} to {l("p10_hi")}&nbsp;s and the ninetieth {l("p90_lo")} to {l("p90_hi")}. Each match
            has {l("touches_lo")} to {l("touches_hi")} touches with {d("touch_min")} dribbles or more.
          </p>
          <p>
            Against the height, {l("windows")} dribbles have the ball at every frame of their window. In {l("offset_zero")} of the{" "}
            {l("matches")} matches the median offset is zero, and so is the median of its size: the events and the height agree
            on the frame more often than not. The lowest height is within {d("near")} frames of the event in {l("near_lo")} to{" "}
            {l("near_hi")}&nbsp;% of the windows, and at the window&apos;s edge, with no low point inside it, in {l("edge_lo")} to{" "}
            {l("edge_hi")}&nbsp;%. And {l("shared_lo")} to {l("shared_hi")} pairs per match, {l("shared_pct_lo")} to{" "}
            {l("shared_pct_hi")}&nbsp;% of the pairs, are two dribbles on one low point, like the pair of the example.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            Two files that describe one action are two witnesses, not one truth. Matching them, event by event, is the first test
            before using either: here they agree on the frame in most dribbles, and the few places where they do not are visible,
            countable and small. A dribble counted twice becomes a short interval, and a short interval pulls a median down a
            little and a mean more.
          </p>
          <p>
            The two ways of reading a rhythm answer different questions. The events say when the provider placed each dribble; the
            autocorrelation says how regularly the height swings, and it needs no labels to say it. When both are at hand, reading
            one against the other is how each is checked.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              The dribble&apos;s frame is the provider&apos;s. How its model places the event is not in the dictionary, so an
              offset says where the two files differ, not which one is right.
            </li>
            <li>
              The ball&apos;s heights are used as the file gives them, at every frame, with no filter on any flag: they are the
              provider&apos;s, wherever they come from.
            </li>
            <li>
              The window&apos;s reach is a choice. A lowest height at its edge says the window holds no low point; a wider window
              could find one, and could also find the bounce before or after.
            </li>
            <li>
              Intervals are measured inside one touch only: a touch with a single dribble has none, and the time between two
              touches is not a bounce.
            </li>
            <li>The autocorrelation is read on one touch. Across ten matches the lesson counts the events, not the height&apos;s period.</li>
            <li>
              The selection. Of {l("dribbles_all")} dribbles with a frame, {l("no_window")} miss the ball&apos;s height at a frame of
              their window; the rest, {l("windows")}, are the table&apos;s windows.
            </li>
            <li>Basketball only.</li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>
              In the figure, pick dribble {l("shared_first")} and then dribble {l("shared")}. Where is each one&apos;s lowest
              height, and which event sits closer to it?
            </li>
            <li>Pick dribble {x(0, "n")}. How far is its lowest height from the floor?</li>
            <li>
              With pencil and paper: a ball that meets the floor at speed <M><mi>v</mi></M>, filmed at <M><mi>f</mi></M> frames per
              second. How high above the floor can the lowest frame be, at most?
            </li>
            <li>
              Run the query below on another match: change the id in both file names and compare the result with that
              match&apos;s row in the table.
            </li>
          </ul>
        </section>

        <Reproduce sql={sql} browser="dribble">
          <p>
            The query is the table&apos;s method in DuckDB, written for the public files of match {d("example.match_id")}: the
            events file for the dribbles and the tracking file for the ball&apos;s height. It needs nothing else: no Track Lab code
            and no intermediate tables.
          </p>
          <ol>
            <li>
              Clone <code>https://github.com/SkillCorner/opendata-basketball</code> with Git LFS, which holds the tracking
              files, and check out <code>4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66</code>.
            </li>
            <li>
              Open a terminal in <code>data/matches/{NATIVE}</code>, next to <code>{NATIVE}_dynamic_events.json</code> and{" "}
              <code>{NATIVE}_tracking_data.jsonl.gz</code>.
            </li>
            <li>
              Save the query as <code>dribble.sql</code> and run <code>duckdb &lt; dribble.sql</code>.
            </li>
          </ol>
          <p>
            It returns {m("dribbles")} dribbles and {m("intervals")} intervals with a median of {m("interval_median_s")}&nbsp;s,
            between {m("interval_p10_s")} and {m("interval_p90_s")} at the tenth and ninetieth percentiles; {m("touches_3")} long
            touches; {m("windows")} windows, with a median offset of {m("offset_median")} and a median size of{" "}
            {m("offset_abs_median")}, {m("near_pct")}&nbsp;% near the event and {m("edge_pct")}&nbsp;% at the edge; a median lowest
            height of {m("low_z_median")}&nbsp;m; and {m("shared_low")} of {m("pairs")} pairs on one low point: that match&apos;s
            row in the table above. The same query, with only the id changed, gives every row; it was checked that way with DuckDB{" "}
            <code>1.5.5</code>.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="nist-autocorrelation" full />: what the autocorrelation of a signal shows.
            </li>
            <li>
              <Cite id="skillcorner-dribbles" full />: the provider&apos;s definitions of every field of a dribble.
            </li>
            <li>
              <a href="/learn/cadence">How many steps per second?</a>, the fifth lesson, for the same reading of a rhythm on a
              body.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures file={DRIBBLE} example={TOUCH} />
    </main>
  );
}
