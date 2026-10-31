import type { ReactNode } from "react";
import { ENTRY, ENTRY_MATCHES, ENTRY_METRICS, ENTRY_RUN, ENTRY_SAMPLES, entryFig } from "../../../lib/learn/entry-data";
import { entryFigures, type EntryFigures } from "../../../lib/learn/entry-figures";
import { qualityFigure } from "../../../lib/learn/gravity-data";
import { figureAt } from "../../../lib/learn/json-figure";
import { HOOK, QUALITY } from "../../../lib/quality";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { EntryFigure } from "./EntryFigure";
import { ExposeFigures } from "./ExposeFigures";
import { PerMatch } from "./PerMatch";

// Lesson 8. No figure is typed: `e(path)` prints a value of entry.json, `q(path)` one of
// quality.json and `l(key)` one of `entryFigures`, each as a `data-fig` the e2e compares with its
// source.
const F = entryFigures(ENTRY, ENTRY_RUN, ENTRY_MATCHES, HOOK.g_data);
const l = (key: keyof EntryFigures) => <Fig name={`learn.${key}`}>{String(F[key])}</Fig>;
const e = (path: string) => <Fig name={`entry.${path}`}>{String(figureAt(ENTRY, "entry", `entry.${path}`))}</Fig>;
const q = (path: string) => <Fig name={path}>{String(qualityFigure(QUALITY, path))}</Fig>;
const REPRO = ENTRY.example.match_id;
const m = (key: keyof typeof ENTRY_METRICS) => q(entryFig(REPRO, ENTRY_METRICS[key]));
const NATIVE = REPRO.replace(/^bb:/, "");

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
const vh = sub("v", <mi>h</mi>);
const vz0 = sub("v", <mrow><mi>z</mi><mn>0</mn></mrow>);
const z0 = sub("z", <mn>0</mn>);
const sq = (x: ReactNode) => (
  <msup>
    <mrow>{x}</mrow>
    <mn>2</mn>
  </msup>
);

export function Lesson({ script }: { script: string }) {
  return (
    <main className="page lesson learn-entry">
      <LessonHead
        n={8}
        title="At what angle does the ball reach the rim?"
        level="Intermediate"
        result={[
          { label: "Gap, reported to required angle", values: [F.gap_lo, F.gap_hi], unit: "°" },
          { label: "Gap on a perfect flight", values: [F.method_gap], unit: "°" },
        ]}
      >
        <p className="lede">
          A made shot drops into the rim at an angle, and the quality checks work it out twice for every one: from the heights the
          file reports near the rim, and from the flight the geometry requires to get there. Over ten matches the reported angle
          is {l("rep_lo")} to {l("rep_hi")}° and the required one {l("req_lo")} to {l("req_hi")}°, a median gap of {l("gap_lo")}{" "}
          to {l("gap_hi")}°, match by match. On this lesson&apos;s shot, a flight that obeys gravity exactly would already show{" "}
          {l("method_gap")}° of it: part of the gap is the method&apos;s own.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            SkillCorner&apos;s basketball events give every field goal a <code>startFrame</code>, <Quote id="skillcorner-shot-start" />{" "}
            (<Cite id="skillcorner-shot-start" />), and an <code>outcome</code>, <Quote id="skillcorner-shot-outcome" /> (
            <Cite id="skillcorner-shot-outcome" />
            ). The tracking gives the ball&apos;s height at every frame, and the provider says of it that{" "}
            <Quote id="skillcorner-ball-z" /> (<Cite id="skillcorner-ball-z" />). The rim does not move: FIBA&apos;s rules say{" "}
            <Quote id="fiba-ring" /> (<Cite id="fiba-ring" />).
          </p>
          <p>
            So a made shot is a flight that starts where the shooter releases it and ends at a known height over a known point.
            Its angle at the rim can be read off the file&apos;s heights, or worked out from where the flight starts, how fast it
            moves across the floor and where it has to end. If the heights were true and the method exact, the two would agree. The first lesson found
            the ball falling slower than gravity; this is a second test of the same heights, through a different number.
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">Two ways to an angle</h2>
          <p>
            Across the floor a flight in free fall keeps its pace: <Quote id="nasa-ballistic" /> (<Cite id="nasa-ballistic" />).
            Measure the horizontal speed <M>{vh}</M> at the start of the flight and the horizontal distance <M><mi>D</mi></M> to
            the rim&apos;s centre, and the time to get there follows:
          </p>
          <Formula label="The flight time to the rim">
            <mrow>
              <mi>T</mi>
              <mo>=</mo>
              {frac(<mi>D</mi>, vh)}
            </mrow>
          </Formula>
          <p>
            Vertically the flight is the first lesson&apos;s parabola. Released at height <M>{z0}</M>, it reaches the rim&apos;s
            height <M><mi>h</mi></M> after <M><mi>T</mi></M> only if it starts with the vertical speed
          </p>
          <Formula label="The vertical speed at the release that reaches the rim after T">
            <mrow>
              {vz0}
              <mo>=</mo>
              {frac(
                <>
                  <mi>h</mi>
                  <mo>−</mo>
                  {z0}
                  <mo>+</mo>
                  <mi>g</mi>
                  {sq(<mi>T</mi>)}
                  <mo>/</mo>
                  <mn>2</mn>
                </>,
                <mi>T</mi>,
              )}
            </mrow>
          </Formula>
          <p>
            and it arrives moving down at <M>{vz0}<mo>−</mo><mi>g</mi><mi>T</mi></M>. The required angle is the one that vertical
            speed makes with <M>{vh}</M>:
          </p>
          <Formula label="The required entry angle">
            <mrow>
              <mi>θ</mi>
              <mo>=</mo>
              <mi>arctan</mi>
              {frac(
                <>
                  <mo>|</mo>
                  {vz0}
                  <mo>−</mo>
                  <mi>g</mi>
                  <mi>T</mi>
                  <mo>|</mo>
                </>,
                vh,
              )}
            </mrow>
          </Formula>
          <p>
            The reported angle uses the same <M>{vh}</M> and the file&apos;s own heights instead: the check fits a least-squares
            line, as in the sixth lesson, through the heights of the last {e("tail_back")} frames before the arrival and the
            arrival itself, and takes its slope as the vertical speed there. One property of that line matters below. On a
            parabola, a line fitted through equally spaced samples has the slope of the tangent at their middle sample. Here that
            is {l("tail_middle")} frames before the arrival, when the ball is still falling more slowly.
          </p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">One shot</h2>
          <p>
            The example is the first lesson&apos;s shot, {e("example.shot_id")} of match {e("example.match_id")}, published from
            its release to the first frame under the rim on the way down: {l("ex_samples")} samples. The check measures{" "}
            <M>{vh}</M> = {l("ex_v_h")}&nbsp;m/s over the first {e("v_h_frames")} samples, from {e("search_offset")} frames after
            the release; the rim&apos;s centre is {l("ex_d")}&nbsp;m away, so <M><mi>T</mi></M> = {l("ex_t")}&nbsp;s and the
            arrival is sample {l("ex_k")}. The required angle is {l("ex_required")}° and the reported one {l("ex_reported")}°: a
            gap of {l("ex_gap")}°.
          </p>
          <EntryFigure
            samples={ENTRY_SAMPLES}
            offset={ENTRY.search_offset}
            constants={ENTRY}
            rimX={ENTRY.example.rim_x}
            hookG={HOOK.g_data}
            heightScale={F.height_scale}
          />
          <p>
            Look at where the arrival sample sits. When <M><mi>T</mi></M> runs out, the tracked ball is still {l("ex_dist_at_k")}
            &nbsp;m short of the rim&apos;s centre and {l("ex_z_at_k")}&nbsp;m up; it comes nearest to the centre{" "}
            {l("ex_closest_after")} frames later, {l("ex_closest_d")}&nbsp;m from it. The file&apos;s ball slows across the floor,
            where the formula assumes it does not, so the check reads the reported angle before the ball has reached the rim.
          </p>
          <p>
            Now give the check a flight with no error at all: the same release point, the same <M>{vh}</M>, and heights that
            follow standard gravity exactly to the rim. The method reads {l("perfect_reported")}° from it, against the{" "}
            {l("ex_required")}° that flight arrives at. That is {l("method_gap")}° of gap with nothing wrong in the data, from the
            line&apos;s lag alone; {l("left_gap")}° of this shot&apos;s gap is left for the data to explain.
          </p>
        </section>

        <section aria-labelledby="sensitive-h">
          <h2 id="sensitive-h">What moves the two angles</h2>
          <p>
            Move g in the figure. Only the required angle answers, by {l("dreq_dg")}° for every m/s². Scale the heights instead:
            each per cent moves the reported angle by {l("drep_ds")}° and the required one by {l("dreq_ds")}°, the second because
            the release height moves too. The rim&apos;s own height barely matters: the check puts it at {l("check_rim_mm")}
            &nbsp;mm, FIBA at {l("fiba_mm")}&nbsp;mm, and the difference moves the required angle by {l("rim_effect")}°.
          </p>
          <p>
            The first lesson ended with two scales that would bring its shot to standard gravity, one at a time. Try both here.
            With g at that lesson&apos;s {l("hook_g")}&nbsp;m/s², the required angle drops to {l("low_g_required")}° and the gap to{" "}
            {l("low_g_gap")}°. With every height multiplied by {l("height_scale")}, the reported angle rises to{" "}
            {l("scaled_reported")}° and the required one to {l("scaled_required")}°, a gap of {l("scaled_gap")}°. Neither closes
            it. As in the first lesson, the files cannot say which, if any, is the cause.
          </p>
        </section>

        <section aria-labelledby="matches-h">
          <h2 id="matches-h">From one shot to ten matches</h2>
          <p>
            The check ran on every made, unblocked shot it could follow: {l("shots_lo")} to {l("shots_hi")} per match,{" "}
            {l("shots")} in all. Each row of the table is one match, as the quality page publishes it.
          </p>
          <PerMatch matches={ENTRY_MATCHES} />
          <p>
            The required angle is {l("req_lo")} to {l("req_hi")}° and the reported one {l("rep_lo")} to {l("rep_hi")}°, a median gap
            of {l("gap_lo")} to {l("gap_hi")}°. The gap is not a constant that could be subtracted: in {l("reo_lo")} to{" "}
            {l("reo_hi")}&nbsp;% of the pairs of shots of a match, the two angles disagree about which of the two came in steeper.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            An entry angle is a small number with a lot riding on it in shooting analysis, and here it is computed two ways from
            one file. Setting a measurement beside what the geometry requires is a test that needs no outside reference; here it
            finds the file&apos;s heights and its geometry disagreeing again, as in the first lesson, this time through an angle.
          </p>
          <p>
            It also shows why a method has to be tried on data with a known answer before its results are read. A line through
            the last heights looks like a harmless way to get a slope; on a perfect flight it is several degrees shallow. Without
            that test, the whole gap would have been charged to the data.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              The flight time comes from the horizontal speed at the start of the flight. The tracked ball slows on the way, so
              the arrival sample can fall before the ball reaches the rim, as it does in the example.
            </li>
            <li>
              The method&apos;s own gap is measured here on one shot. The table&apos;s gaps include it, shot by shot, and the
              lesson does not separate it from the rest.
            </li>
            <li>
              The ball&apos;s positions are used as the file gives them, every frame, with no filter on any flag. The basketball
              ball is flagged as detected in {q("summary.ranges.detection_ball_pct_basketball")}&nbsp;% of rows, and the
              provider&apos;s dictionary defines the flag as <Quote id="skillcorner-tracking" /> (<Cite id="skillcorner-tracking" />
              ).
            </li>
            <li>
              Only made shots: a miss has no known end point. The check drops shots it cannot follow from the release, or whose
              flight time falls outside its limits.
            </li>
            <li>The calibration and control split is the one the quality checks made.</li>
            <li>Basketball only.</li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>Find the g at which the required angle meets the reported one. Is it a gravity any ball could fall with?</li>
            <li>Find the height scale at which the two angles meet, with g at its standard value. What would it say about the file?</li>
            <li>
              With pencil and paper: on a parabola, show that the least-squares line through equally spaced samples has the slope
              of the tangent at the middle one.
            </li>
            <li>
              Run the script below on another match folder and compare what it prints with that match&apos;s row in the table.
            </li>
          </ul>
        </section>

        <Reproduce sql={script} browser="entry">
          <p>
            The script reruns the whole check on the public files of one match and needs nothing but Python&apos;s standard
            library: no Track Lab code and no numpy. Its docstring spells out every rule.
          </p>
          <ol>
            <li>
              Clone <code>https://github.com/SkillCorner/opendata-basketball</code> with Git LFS, which holds the tracking
              files, and check out <code>4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66</code>.
            </li>
            <li>
              Save the script as <code>entry.py</code>, open a terminal in <code>data/matches/{NATIVE}</code> and run{" "}
              <code>python entry.py</code>, or pass another match folder as its argument.
            </li>
          </ol>
          <p>
            It prints {m("shots")} shots, a median reported angle of {m("reported")}°, a median required angle of{" "}
            {m("required")}°, a median gap of {m("gap")}° and {m("reordered")}&nbsp;% of pairs in a different order: that
            match&apos;s row in the table above. Run on every match, it gives every row, to the last decimal published.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="nasa-ballistic" full />: the flight of a ball without drag, worked out from its two components.
            </li>
            <li>
              <Cite id="fiba-ring" full />: the dimensions of the basket.
            </li>
            <li>
              <Cite id="skillcorner-shot-start" full />: the provider&apos;s definitions of every field of a shot.
            </li>
            <li>
              <a href="/learn/gravity">Does the ball obey gravity?</a>, the first lesson, for the same heights and its two
              scales, and <a href="/learn/clock">Does the game clock keep the video&apos;s time?</a> for the line through a
              handful of samples.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures file={ENTRY} run={ENTRY_RUN} matches={ENTRY_MATCHES} hookG={HOOK.g_data} />
    </main>
  );
}
