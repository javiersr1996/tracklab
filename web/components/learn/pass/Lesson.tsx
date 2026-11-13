import { DUCKDB_VERSION } from "../../../lib/platform";
import type { ReactNode } from "react";
import { figureAt, matchFig } from "../../../lib/learn/json-figure";
import { PASS, PASS_EXAMPLES } from "../../../lib/learn/pass-data";
import { lessonPassFigures, type PassLessonFigures } from "../../../lib/learn/pass-figures";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { ExposeFigures } from "./ExposeFigures";
import { PassArc } from "./PassArc";
import { PerMatch } from "./PerMatch";

// Lesson 7. No figure is typed: `p(path)` prints a value of pass.json, `l(key)` one of
// `lessonPassFigures` and `x(i, key)` one of its example passes, each as a `data-fig` the e2e
// compares with its source.
const F = lessonPassFigures(PASS, PASS_EXAMPLES);
type One = PassLessonFigures["passes"][number];
const l = (key: Exclude<keyof PassLessonFigures, "passes">) => <Fig name={`learn.${key}`}>{String(F[key])}</Fig>;
const x = (i: number, key: keyof One) => <Fig name={`learn.passes.${i}.${key}`}>{String(F.passes[i][key])}</Fig>;
const p = (path: string) => <Fig name={`pass.${path}`}>{String(figureAt(PASS, "pass", `pass.${path}`))}</Fig>;
const REPRO = PASS.example.match_id;
const m = (field: string) => <Fig name={matchFig("pass", REPRO, field)}>{String(figureAt(PASS, "pass", matchFig("pass", REPRO, field)))}</Fig>;
const NATIVE = REPRO.replace(/^bb:/, "");
const B = F.bounce - 1;
const LAST = F.passes.length - 1;

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
const BOLD_R = "𝐫";
const r = (i: ReactNode) => (
  <msub>
    <mi>{BOLD_R}</mi>
    <mrow>{i}</mrow>
  </msub>
);
const norm = (inner: ReactNode) => (
  <>
    <mo>|</mo>
    {inner}
    <mo>|</mo>
  </>
);

export function Lesson({ sql }: { sql: string }) {
  return (
    <main id="main" className="page lesson learn-pass">
      <LessonHead
        n={7}
        title="How fast does a pass travel?"
        level="Intermediate"
        result={[
          { label: "Median pass by the ball, per match", values: [F.chord_lo, F.chord_hi], unit: "m/s" },
          { label: "By the provider's distance", values: [F.dist_lo, F.dist_hi], unit: "m/s" },
        ]}
      >
        <p className="lede">
          The provider&apos;s passes come with a distance and two frames, so a pass&apos;s speed looks one division away. But that
          distance is the gap between passer and receiver when the pass starts, and the ball covers only {l("share_lo")} to{" "}
          {l("share_hi")}&nbsp;% of it in the median pass, match by match. Measured by the ball itself, the median pass travels at{" "}
          {l("chord_lo")} to {l("chord_hi")}&nbsp;m/s; the provider&apos;s distance over the same time gives {l("dist_lo")} to{" "}
          {l("dist_hi")}.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            SkillCorner&apos;s basketball events list every pass with two frames: <code>startFrame</code>,{" "}
            <Quote id="skillcorner-pass-start" /> (<Cite id="skillcorner-pass-start" />), and <code>endFrame</code>,{" "}
            <Quote id="skillcorner-pass-end" /> (<Cite id="skillcorner-pass-end" />). It also gives a <code>distance</code>:{" "}
            <Quote id="skillcorner-pass-distance" /> (<Cite id="skillcorner-pass-distance" />). Divide one by the time between the
            other two and a pass has a speed.
          </p>
          <p>
            Read the two fields that distance is built from, though. <code>passerLoc</code> is the{" "}
            <Quote id="skillcorner-pass-passer-loc" /> (<Cite id="skillcorner-pass-passer-loc" />), and <code>receiverLoc</code>{" "}
            the <Quote id="skillcorner-pass-receiver-loc" /> (<Cite id="skillcorner-pass-receiver-loc" />). Both are taken at the
            release. The distance is a fact about two players at one instant. Is it what the ball travels?
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">Chord and path</h2>
          <p>
            The tracking gives the ball&apos;s position <M>{r(<mi>k</mi>)}</M> in three dimensions at every frame{" "}
            <M><mi>k</mi></M> of the pass, from <M><mn>0</mn></M> at the release to <M><mi>N</mi></M> at the reception. Two lengths
            come out of those positions. The first is the chord: <Quote id="mathworld-chord" /> (<Cite id="mathworld-chord" />
            ), here the segment from the ball&apos;s first position to its last. Over the pass&apos;s time it gives the chord speed,
            with <M><mi>f</mi></M> frames per second:
          </p>
          <Formula label="The chord speed of a pass">
            <mrow>
              <mi>v</mi>
              <mo>=</mo>
              {frac(norm(<>{r(<mi>N</mi>)}<mo>−</mo>{r(<mn>0</mn>)}</>), <><mi>N</mi><mo>/</mo><mi>f</mi></>)}
            </mrow>
          </Formula>
          <p>
            The second is the path, which follows the ball. <Quote id="mathworld-arc-length" /> (<Cite id="mathworld-arc-length" />
            ) is what arc length means for a smooth curve; with one position per frame it becomes a sum of steps:
          </p>
          <Formula label="The path of the ball over a pass">
            <mrow>
              <mi>L</mi>
              <mo>=</mo>
              <msubsup>
                <mo>∑</mo>
                <mrow>
                  <mi>k</mi>
                  <mo>=</mo>
                  <mn>1</mn>
                </mrow>
                <mi>N</mi>
              </msubsup>
              {norm(<>{r(<mi>k</mi>)}<mo>−</mo>{r(<mrow><mi>k</mi><mo>−</mo><mn>1</mn></mrow>)}</>)}
            </mrow>
          </Formula>
          <p>
            No path is shorter than its chord, and they are equal only when every step points the same way. Their ratio says how
            much the ball&apos;s route bends: a pass through the air barely, a bounce pass, which goes down to the floor and up
            again, more. The chord speed is the size of the ball&apos;s average velocity over the pass. It does not say how fast
            the ball was at any one frame; the second lesson is about that.
          </p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">One possession</h2>
          <p>
            The figure reads the {l("example_n")} passes of a published possession of match {p("example.match_id")}, the one the
            second lesson follows a player through. Take the first. The provider&apos;s distance is {x(0, "distance_m")}&nbsp;m, and
            the two players&apos; positions in the possession at the first frame are {x(0, "separation_m")}&nbsp;m apart, to the
            centimetre the possession is written at. The ball&apos;s chord is {x(0, "chord_m")}&nbsp;m. At the first frame the ball
            is {x(0, "from_passer_m")}&nbsp;m from where the tracking puts the passer, and at the last {x(0, "to_receiver_m")}
            &nbsp;m from the receiver: a player is tracked where they stand, not where the ball is held. In each of the{" "}
            {l("example_n")} passes the ball is already moving away from the passer at the first frame and is still closing on
            the receiver at the last, so the provider&apos;s frames do not mark the ball leaving one player or reaching the other.
          </p>
          <PassArc passes={PASS_EXAMPLES} fps={PASS.fps} />
          <p>
            Over its {x(0, "seconds")}&nbsp;s the first pass&apos;s chord gives {x(0, "chord_speed")}&nbsp;m/s; the provider&apos;s
            distance over the same time would give {x(0, "distance_speed")}. Its path, {x(0, "path_m")}&nbsp;m, is{" "}
            {x(0, "path_pct")}&nbsp;% longer than its chord. Pass {l("bounce")} is a bounce pass: the ball drops to{" "}
            {x(B, "z_min")}&nbsp;m and its path is {x(B, "path_pct")}&nbsp;% longer than its chord. In the last pass the ball covers
            only {x(LAST, "share_pct")}&nbsp;% of the provider&apos;s distance: it starts {x(LAST, "from_passer_m")}&nbsp;m from the
            passer&apos;s tracked position.
          </p>
          <figure className="learn-fig surface-dark" data-figure="passes">
            <div className="table-scroll">
              <table className="learn-matches">
                <thead>
                  <tr>
                    <th scope="col">pass</th>
                    <th scope="col">frames</th>
                    <th scope="col">provider&apos;s distance (m)</th>
                    <th scope="col">ball&apos;s chord (m)</th>
                    <th scope="col">ball&apos;s path (m)</th>
                    <th scope="col">chord speed (m/s)</th>
                    <th scope="col">distance over time (m/s)</th>
                  </tr>
                </thead>
                <tbody>
                  {F.passes.map((_, i) => (
                    <tr key={i} data-pass={PASS.example.passes[i].pass_id}>
                      <td>{i + 1}</td>
                      <td>{x(i, "frames")}</td>
                      <td>{x(i, "distance_m")}</td>
                      <td>{x(i, "chord_m")}</td>
                      <td>{x(i, "path_m")}</td>
                      <td>{x(i, "chord_speed")}</td>
                      <td>{x(i, "distance_speed")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <figcaption>
              The passes of the possession in the figure above, from its published positions. The provider&apos;s distance is the
              event&apos;s own figure, in metres.
            </figcaption>
          </figure>
        </section>

        <section aria-labelledby="distance-h">
          <h2 id="distance-h">What the provider&apos;s distance measures</h2>
          <p>
            The dictionary already says it: the distance between two players at the release. The pipeline checked it against the
            tracking on every pass the table below measures: on all {l("separation_n")} of them, the distance and the two
            players&apos; tracked separation at the start frame are the same number, the largest difference in any match being{" "}
            {l("separation_gap")}&nbsp;m. The provider computed it from the same positions. It is a fine figure for the spacing of a pass. It is not the ball&apos;s
            journey, and divided by the pass&apos;s time it comes out at {l("speed_ratio_lo")} to {l("speed_ratio_hi")} times the
            ball&apos;s chord speed in the median pass, match by match.
          </p>
        </section>

        <section aria-labelledby="matches-h">
          <h2 id="matches-h">From one possession to ten matches</h2>
          <p>
            The pipeline measured every complete pass that ends after it starts and has the ball at every frame of the way:{" "}
            {l("n_lo")} to {l("n_hi")} per match, {l("measured")} in all. Each row of the table is one match.
          </p>
          <PerMatch matches={PASS.matches} />
          <p>
            The median pass travels at {l("chord_lo")} to {l("chord_hi")}&nbsp;m/s, and the ninetieth percentile is{" "}
            {l("p90_lo")} to {l("p90_hi")}&nbsp;m/s. Its path is {l("path_pct_lo")} to {l("path_pct_hi")}&nbsp;% longer than its
            chord: most passes take nearly the shortest way, and the bounce passes are the exception, not the rule. The ball
            covers {l("share_lo")} to {l("share_hi")}&nbsp;% of the provider&apos;s distance in the median pass.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            A field&apos;s name is not its definition. <code>distance</code> on a pass reads like the length of the pass, and the
            division it invites gives speeds {l("speed_ratio_lo")} to {l("speed_ratio_hi")} times the ball&apos;s. The dictionary said what it was; the tracking confirmed
            it in one join. Reading the definition, and checking it against the raw positions, comes before any figure built on a
            field.
          </p>
          <p>
            The chord and the path are also two answers to two questions. How quickly the ball gets from one player to the other
            is the chord&apos;s; how far it went on the way is the path&apos;s. A bounce pass makes them differ, and so does a lob.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              The release and reception frames are the provider&apos;s. In the example the ball has already left the passer&apos;s
              tracked position at the first and has not yet reached the receiver&apos;s at the last, and the chord counts whatever
              the ball does between them.
            </li>
            <li>
              The ball&apos;s positions are used as the file gives them, at every frame, with no filter on any flag: they are the
              provider&apos;s, wherever they come from.
            </li>
            <li>
              The chord speed is an average over the pass. How the ball&apos;s speed changes on the way, through the air or
              off the floor, is not in it.
            </li>
            <li>
              The example shows where the difference between the distance and the chord goes in four passes. Over ten matches the
              lesson measures the difference; it does not split it between the passer&apos;s reach, the receiver&apos;s reach and
              the receiver&apos;s movement.
            </li>
            <li>
              The selection. Of {l("complete")} complete passes with a start, an end and a distance, {l("not_forward")} do not end
              after they start and {l("no_ball")} miss the ball at a frame of the way. The rest, {l("measured")}, are the
              table&apos;s.
            </li>
            <li>Basketball only.</li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>In the figure, pick the last pass. Where is the ball at the first frame, and where is the passer?</li>
            <li>Pick the bounce pass. At which frame does the ball reach the floor, and what does the chord miss?</li>
            <li>
              With pencil and paper: a bounce pass that leaves and arrives at the same height and bounces halfway. Write its path
              as a function of that height and its chord. When is it much longer than the chord?
            </li>
            <li>
              Run the query below on another match: change the id in both file names and compare the result with that
              match&apos;s row in the table.
            </li>
          </ul>
        </section>

        <Reproduce sql={sql} browser="pass">
          <p>
            The query is the table&apos;s method in DuckDB, written for the public files of match {p("example.match_id")}: the
            events file for the passes and the tracking file for the ball. It needs nothing else: no Pitch & Parquet code and no
            intermediate tables.
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
              Save the query as <code>pass.sql</code> and run <code>duckdb &lt; pass.sql</code>.
            </li>
          </ol>
          <p>
            It returns {m("n")} passes, a median chord speed of {m("chord_speed_median")}&nbsp;m/s and a ninetieth percentile of{" "}
            {m("chord_speed_p90")}, a median path over chord of {m("path_over_chord")}, the provider&apos;s distance over time at{" "}
            {m("distance_speed_median")}&nbsp;m/s and a median chord over distance of {m("chord_over_distance")}: that match&apos;s
            row in the table above. The same query, with only the id changed, gives every row; it was checked that way with DuckDB{" "}
            <code>{DUCKDB_VERSION}</code>.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="mathworld-chord" full /> and <Cite id="mathworld-arc-length" full />: the two lengths of a curve.
            </li>
            <li>
              <Cite id="skillcorner-pass-distance" full />: the provider&apos;s definitions of every field of a pass.
            </li>
            <li>
              <a href="/learn/speed">Where does the provider&apos;s speed come from?</a>, the second lesson, for speed at one frame
              rather than over a pass.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures file={PASS} examples={PASS_EXAMPLES} />
    </main>
  );
}
