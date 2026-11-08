import type { ReactNode } from "react";
import {
  CLOCK_WINDOW_MS,
  clockTrack,
  coordinatesFigures,
  frameView,
  HOME_STEMS,
  MATCHES,
  possession,
  possessionFig,
  publishedFigure,
  statsFig,
} from "../../../lib/learn/coordinates-data";
import { printed } from "../../../lib/learn/coordinates";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { ClockFigure } from "./ClockFigure";
import { ExposeFigures } from "./ExposeFigures";
import { FrameFigure } from "./FrameFigure";
import { PerMatch } from "./PerMatch";

// Lesson 3. No figure is typed: `f(path)` prints a value of a published file (`publishedFigure`)
// and `l(path)` one of `coordinatesFigures`, each as a `data-fig` the e2e compares with its source.
// Large counts carry thousands separators and negatives a minus sign; the e2e strips both.
const F = coordinatesFigures();
const BB = HOME_STEMS.basketball;
const FB = HOME_STEMS.football;

const dig = (path: string): unknown =>
  path.split(".").reduce<unknown>((at, k) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[k] : undefined), F);
const l = (path: string) => <Fig name={`learn.${path}`}>{printed(dig(path))}</Fig>;
const f = (path: string) => <Fig name={path}>{printed(publishedFigure(path))}</Fig>;
const pf = (stem: string, path: string) => f(possessionFig(stem, path));

const mi = (x: string) => <mi>{x}</mi>;
const sub = (x: string, i: string) => (
  <msub>
    <mi>{x}</mi>
    <mi>{i}</mi>
  </msub>
);
// A pair in brackets, on one line: MathML's brackets around a table do not stretch without a math font.
const pair = (a: ReactNode, b: ReactNode) => (
  <mrow>
    <mo>(</mo>
    {a}
    <mo>,</mo>
    {b}
    <mo>)</mo>
  </mrow>
);
const times = (a: string, b: string) => (
  <mrow>
    <mi>{a}</mi>
    <mi>{b}</mi>
  </mrow>
);
const minusOne = (
  <M>
    <mi>k</mi>
    <mo>=</mo>
    <mo>−</mo>
    <mn>1</mn>
  </M>
);
const plusOne = (
  <M>
    <mi>k</mi>
    <mo>=</mo>
    <mo>+</mo>
    <mn>1</mn>
  </M>
);

export function Lesson({ sql }: { sql: string }) {
  const views = [frameView(BB), frameView(FB)];
  const tracks = [clockTrack(BB), clockTrack(FB)];
  // The highlighted player's jersey, as the possession file has it.
  const jersey = (stem: string, k: number) => pf(stem, `entities.${possession(stem).entities.findIndex((e) => e.i === views[k].highlight)}.jersey`);
  return (
    <main id="main" className="page lesson learn-coordinates">
      <LessonHead
        n={3}
        title="Can a court and a pitch share one table?"
        level="Foundations"
        result={[
          { label: "One basketball frame", values: [F.step_bb_ms], unit: "ms" },
          { label: "One football frame", values: [F.step_fb_ms], unit: "ms" },
        ]}
      >
        <p className="lede">
          A basketball court arrives in feet and a football pitch in metres; one clock ticks every {l("step_bb_ms")}&nbsp;ms,
          the other every {l("step_fb_ms")}. Track Lab keeps both in one table and reads either with the same query. A
          little geometry and a little arithmetic on time make that work, and both fit on one page.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            SkillCorner&apos;s open data comes in two bundles that were not made to agree. The basketball tracking gives
            every position in feet: <Quote id="skillcorner-bb-coords" /> (<Cite id="skillcorner-bb-coords" />). The
            football tracking gives it in metres: <Quote id="skillcorner-fb-coords" /> (
            <Cite id="skillcorner-fb-coords" />). The court is sampled {pf(BB, "sample_rate_hz")} times a second and the
            pitch {pf(FB, "sample_rate_hz")}. In both sports the teams change ends, so the way a team attacks depends on
            the period.
          </p>
          <p>
            The home page says the two live in one table and come back with one query,{" "}
            <code>SELECT * FROM frames WHERE sport = ?</code>. For that to hold, a row has to mean the same thing
            whichever sport wrote it: the same unit, the same origin and axes, the same kind of clock, and no hidden
            assumption about direction. This lesson builds each of those on the two possessions the home page plays, then
            looks at what they add up to, match by match.
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">Points, frames and affine maps</h2>
          <p>
            A pair of coordinates is not yet a position. It becomes one once you say what it is measured from: a frame
            of reference fixes an origin, two axes and a unit. The same player on the same court has different numbers in
            different frames, and changing frame is a map from one set of numbers to the other. Every change this lesson
            needs is affine, a linear part and a shift:
          </p>
          <Formula label="An affine map of the plane">
            <mrow>
              <msup>
                <mi>p</mi>
                <mo>′</mo>
              </msup>
              <mo>=</mo>
              <mi>A</mi>
              <mi>p</mi>
              <mo>+</mo>
              <mi>b</mi>
              <mo>,</mo>
              <mspace width="1em" />
              <mi>p</mi>
              <mo>=</mo>
              {pair(mi("x"), mi("y"))}
            </mrow>
          </Formula>
          <p>Three ingredients do all the work here.</p>
          <h3>The unit</h3>
          <p>
            A foot is {l("foot_m")}&nbsp;m, exactly: the NIST guide lists the factor in bold and says{" "}
            <Quote id="nist-811-b8" /> (<Cite id="nist-811-b8" />). Converting multiplies both coordinates by{" "}
            <M>
              <mi>s</mi>
            </M>
            , so <M>
              <mi>A</mi>
              <mo>=</mo>
              <mi>s</mi>
              <mi>I</mi>
            </M>{" "}
            with <M><mi>I</mi></M> the identity. For football <M><mi>s</mi></M> is one.
          </p>
          <h3>The origin</h3>
          <p>
            Both providers already put it at the centre of the surface, with x along the long side, so the shift{" "}
            <M><mi>b</mi></M> is zero for both. That is a convenience of these two bundles, not a law, and the example
            below shows what a corner origin would cost.
          </p>
          <h3>The direction</h3>
          <p>
            The teams change ends, so a team&apos;s attack runs towards +x in one period and −x in another. Track Lab
            records it as an attack sign <M><mi>k</mi></M>, plus or minus one, and turns a frame for a team by
            multiplying both coordinates by it:
          </p>
          <Formula label="The attack sign applied to a point">
            <mrow>
              <mi>k</mi>
              <mi>I</mi>
              {pair(mi("x"), mi("y"))}
              <mo>=</mo>
              {pair(times("k", "x"), times("k", "y"))}
            </mrow>
          </Formula>
          <p>With {minusOne} that is half a turn about the centre, not a mirror. A mirror changes x alone,</p>
          <Formula label="A mirror in the y axis">
            <mrow>
              {pair(mi("x"), mi("y"))}
              <mo>↦</mo>
              {pair(
                <mrow>
                  <mo>−</mo>
                  <mi>x</mi>
                </mrow>,
                mi("y"),
              )}
            </mrow>
          </Formula>
          <p>
            and the difference is the determinant: plus one for the turn, minus one for the mirror. MathWorld calls an orthogonal
            matrix with determinant one <Quote id="mathworld-rotation" /> (<Cite id="mathworld-rotation" />). A turn
            keeps a team&apos;s left wing on its left; a mirror swaps the wings.
          </p>
          <p>Put together, a provider&apos;s point reaches Track Lab&apos;s frame in one product:</p>
          <Formula label="From the provider's frame to Track Lab's">
            <mrow>
              {sub("p", "common")}
              <mo>=</mo>
              <mi>k</mi>
              <mi>s</mi>
              {sub("p", "provider")}
            </mrow>
          </Formula>
          <p>Both factors are numbers times the identity, so their order does not matter and nothing needs a shift.</p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">Two possessions</h2>
          <p>
            The home page alternates two possessions, one from basketball match {pf(BB, "match.match_id")} and one
            from football match {pf(FB, "match.match_id")}. Their first frames are below, taken through the steps a
            row goes through on its way into the table.
          </p>
          <FrameFigure views={views} feetBound={F.feet_bound} />
          <p>
            Start with the court as delivered. The axes read in feet, and the court runs {l("court_ft_length")} of them by{" "}
            {l("court_ft_width")}. Step to metres and nothing on the screen moves; only the numbers change, each multiplied
            by <M><mi>s</mi></M>. That is what a change of unit is. A query that skipped it would put these players on a
            court {l("court_ft_length")}&nbsp;m long, nearer the length of the pitch ({pf(FB, "surface.length_m")}
            &nbsp;m) than of any court.
          </p>
          <p>
            The pitch needs no unit step. Neither possession needs a turn either: in both, the team with the ball
            already attacks towards +x, so its sign is {plusOne}. That is a coincidence of these two possessions, not a
            rule. Turn the frame for the other team and {minusOne}. Then try the mirror and follow number {jersey(BB, 0)} of
            the team with the ball: the turn moves him from the top half of the picture to the bottom and keeps him on
            the same side of his own team&apos;s attack; the mirror leaves him at the top and so on the wrong side of it.
          </p>
          <p>
            The centred origin is what makes the turn a plain multiplication. Measure the pitch from a corner instead
            and number {jersey(FB, 1)} of the football frame sits at ({l("corner.point.0")}, {l("corner.point.1")}). Multiply
            that by minus one and you get ({l("corner.negated.0")}, {l("corner.negated.1")}), off the pitch altogether.
            Half a turn about the centre is now the pitch&apos;s length and width minus the point:
          </p>
          <Formula label="Half a turn about the centre for a corner origin">
            <mrow>
              <msup>
                <mi>q</mi>
                <mo>′</mo>
              </msup>
              <mo>=</mo>
              {pair(mi("L"), mi("W"))}
              <mo>−</mo>
              <mi>q</mi>
            </mrow>
          </Formula>
          <p>
            which gives ({l("corner.turned.0")}, {l("corner.turned.1")}). With a shift in the map the order of the steps
            matters, and the safe habit is to bring every provider to a centred frame before turning anything.
          </p>
        </section>

        <section aria-labelledby="time-h">
          <h2 id="time-h">Two clocks on one axis</h2>
          <p>
            Space is half the problem. A row also carries a time, and the sports sample at different rates. Track Lab
            keeps each at its own: a row is a native frame of the provider, and its time is the frame number over the
            rate,
          </p>
          <Formula label="The time of a native frame">
            <mrow>
              {sub("t", "ms")}
              <mo>=</mo>
              <mfrac>
                <mrow>
                  <mn>1000</mn>
                  <mo>·</mo>
                  <mi>frame</mi>
                </mrow>
                <mi>rate</mi>
              </mfrac>
            </mrow>
          </Formula>
          <p>
            The court&apos;s possession starts at frame {l("frame_bb")}, {pf(BB, "frames.0.t")}&nbsp;ms into the video; the
            pitch&apos;s at frame {l("frame_fb")}, {pf(FB, "frames.0.t")}&nbsp;ms into its own. Nothing is resampled on
            the way in, so the table holds only what the providers sent.
          </p>
          <p>
            Reading the two at the same instant is another matter. The replay on the home page draws both sports with
            the same code: for an instant <M><mi>t</mi></M> between samples at <M>{sub("t", "a")}</M> and{" "}
            <M>{sub("t", "b")}</M>, it takes a weighted average of the two positions,
          </p>
          <Formula label="Linear interpolation between two samples">
            <mrow>
              <mi>p</mi>
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <mo>=</mo>
              <mo>(</mo>
              <mn>1</mn>
              <mo>−</mo>
              <mi>α</mi>
              <mo>)</mo>
              {sub("p", "a")}
              <mo>+</mo>
              <mi>α</mi>
              {sub("p", "b")}
              <mo>,</mo>
              <mspace width="1em" />
              <mi>α</mi>
              <mo>=</mo>
              <mfrac>
                <mrow>
                  <mi>t</mi>
                  <mo>−</mo>
                  {sub("t", "a")}
                </mrow>
                <mrow>
                  {sub("t", "b")}
                  <mo>−</mo>
                  {sub("t", "a")}
                </mrow>
              </mfrac>
            </mrow>
          </Formula>
          <p>
            The weights are never negative and they add up to one, the property that kept a smoother from flattening a
            parabola in the <a href="/learn/gravity">gravity lesson</a>. The figure reads the ball&apos;s x over the first
            second of both possessions with the replay&apos;s own engine.
          </p>
          <ClockFigure tracks={tracks} shared={F.shared_ms} windowMs={CLOCK_WINDOW_MS} />
          <p>
            The two clocks agree only every {l("shared_ms")}&nbsp;ms, the least common multiple of {l("step_bb_ms")} and{" "}
            {l("step_fb_ms")}: one court frame in {l("every_bb")} and one pitch frame in {l("every_fb")}. Put a football
            track on the court&apos;s clock and {l("missing_fb_on_bb")} instants in every {l("every_bb")} are averages; put
            a basketball track on the pitch&apos;s clock and {l("missing_bb_on_fb")} in {l("every_fb")} is. The provider
            does the same when it must. Its football body pose runs faster than its tracking, and the README says so:{" "}
            <Quote id="skillcorner-fb-bodypose" /> (<Cite id="skillcorner-fb-bodypose" />).
          </p>
          <p>
            Weights that add up to one have a second consequence. In MathWorld&apos;s words,{" "}
            <Quote id="mathworld-affine" /> (<Cite id="mathworld-affine" />), and a weighted average whose weights add up
            to one is such a combination. So converting and turning a frame before the replay averages two samples, or
            after, lands on the same point. That is why the replay can interpolate the stored metres and turn the
            picture only when a reader ticks <q>normalize attack</q>.
          </p>
        </section>

        <section aria-labelledby="table-h">
          <h2 id="table-h">One table, and the sign kept apart</h2>
          <p>
            With those pieces the table is short to describe. <code>frames</code> holds one row per match, native frame
            and entity, with <code>x_m</code> and <code>y_m</code> in metres in the venue frame, the frame both providers
            deliver, and <code>t_ms</code> at the sport&apos;s own rate. What it does not hold is the attack sign. That
            lives in <code>dim_team_period</code>, one row per match, period and team. In basketball the build reads it
            from the provider&apos;s <code>leftHoop</code>, <Quote id="skillcorner-bb-lefthoop" /> (
            <Cite id="skillcorner-bb-lefthoop" />); in football, from the side each team starts the period on.
          </p>
          <p>
            The published row counts show its shape. Basketball has {f(statsFig("dim_period", "basketball"))} periods
            and {f(statsFig("dim_team_period", "basketball"))} team periods, {l("team_period_ratio_bb")} per period, one
            for each team; football&apos;s counts keep the same ratio, {l("team_period_ratio_fb")}. Turning a frame is then
            a join and one multiplication, in a view called <code>frames_attacking</code>:{" "}
            <code>tp.attack_sign * f.x_m AS x_att_m</code>.
          </p>
          <p>
            Keeping the sign out of <code>frames</code> is deliberate. Both teams are on the surface in every frame, and
            a frame turned for one of them is backwards for the other. Baked into the rows, the sign would make every
            row right for half the people reading it.
          </p>
        </section>

        <section aria-labelledby="matches-h">
          <h2 id="matches-h">From two possessions to every match</h2>
          <p>
            Each match leaves its own mark on the table. The rate belongs to the sport, but whether the frames really
            step at it is a property of the file, and so are the surface and the row count. The table covers the{" "}
            {l("matches_bb")} basketball matches and {l("matches_fb")} of the football ones.
          </p>
          <PerMatch matches={MATCHES} />
          <p>
            Every frame step checked lands exactly on the rate, in every match: {f("quality.summary.ranges.clock_step_exact_basketball")}
            &nbsp;% on the court, where the provider&apos;s millisecond clock moves by one step each time the frame number
            moves by one, and {f("quality.summary.ranges.clock_step_exact_football")}&nbsp;% on the pitch, where there is
            no separate clock and the frame numbers are simply contiguous. The steps cover a median of{" "}
            {l("median_minutes_bb")} minutes of video per basketball match and {l("median_minutes_fb")} per football match.
          </p>
          <p>
            The row counts come out close, a median of {l("median_rows_bb")} per basketball match against{" "}
            {l("median_rows_fb")} per football match, although the court is sampled {l("rate_ratio")} times as often.
            The other factor is the number of entities: a court frame holds at most {pf(BB, "entities.length")}, the
            players and the ball, and a pitch frame {pf(FB, "entities.length")}. That caps a second of video at{" "}
            {l("max_rows_s_bb")} rows on the court and {l("max_rows_s_fb")} on the pitch, and a frame where nobody is
            tracked adds none.
          </p>
          <p>
            The surface, unlike the rate, can change within a sport. Every published court is {l("surfaces_bb.0.0")} by{" "}
            {l("surfaces_bb.0.1")}&nbsp;m, while the published pitches come in two sizes, {l("surfaces_fb.0.0")} by{" "}
            {l("surfaces_fb.0.1")} and {l("surfaces_fb.1.0")} by {l("surfaces_fb.1.1")}&nbsp;m. The same x near a goal
            line is a different distance from goal on each, which is why the surface is a column of the match and not a
            constant of the sport. The signs, finally, are a reminder that plus one is no default: of the published
            possessions, {l("signs_plus")} carry it and {l("signs_minus")} carry minus one.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            Every number derived from positions inherits these steps. A distance in feet set beside one in metres is
            off by a factor of {l("ft_per_m")}, and so is a speed. Half a turn moves no point relative to another, so
            distances and angles inside a frame survive it untouched, and a team&apos;s attack can be normalised without
            changing a single measurement made within the frame. A mirror keeps distances too, but it swaps the sides,
            and a statistic about the left wing would quietly become one about the right.
          </p>
          <p>
            A common clock is a choice, not a given. Either the table keeps native rates, as Track Lab does, and every
            reader interpolates for itself, or a build resamples once and every row after that is partly an average.
            The same questions come back with any new provider: what the unit is, where the origin sits and which way
            the axes run, and what the clock counts. Answer them with a map of the form{" "}
            <M>
              <mi>k</mi>
              <mi>s</mi>
              <mi>p</mi>
              <mo>+</mo>
              <mi>b</mi>
            </M>
            , check it on a frame you can see, and the new source joins the same table.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              The feet in the first figure are the published metres divided back by <M><mi>s</mi></M>, not the
              provider&apos;s own numbers. The query below reads those.
            </li>
            <li>
              <code>dim_team_period</code> itself is not published. The lesson shows the attack sign only for the period
              of each published possession, and the table&apos;s shape from its row counts.
            </li>
            <li>Surfaces are known here only for matches with a published possession; the others say so.</li>
            <li>
              Neither clock check uses an outside reference. On the court it compares two counters from the same
              provider; on the pitch it only checks that frame numbers are contiguous.
            </li>
            <li>
              Interpolation here is a way to read between samples. Nothing in this lesson measures how the motion
              between two samples departs from their average.
            </li>
            <li>
              The football rows cover {l("matches_fb")} of the bundle&apos;s {f("quality.summary.football_matches")} matches.
            </li>
            <li>
              Only coordinates on the surface are treated. The cameras&apos; image coordinates and the frame the
              providers write their events in are left out.
            </li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>
              In the first figure, pick the mirror and then the turn for the other team, and follow number {jersey(BB, 0)} of the team with the ball.
              Which one would a coach accept as the same play seen from the other bench?
            </li>
            <li>
              Work out by hand where a corner of the court lands at each step. Which steps move it, and which only
              rename it?
            </li>
            <li>
              In the second figure, find an instant where the court&apos;s α is zero and the pitch&apos;s is not, and
              one where both are zero.
            </li>
            <li>
              Write <M><mi>A</mi></M> and <M><mi>b</mi></M> for a provider that measures in yards from the bottom left
              corner, with x along the long side.
            </li>
            <li>
              Run the query below on another match: change the ids, and the <code>wallClock</code> to the first frame of
              that match&apos;s possession, and compare with its row in the table.
            </li>
          </ul>
        </section>

        <Reproduce sql={sql} browser="coordinates">
          <p>
            The query rebuilds the first figure&apos;s numbers from SkillCorner&apos;s public files with DuckDB: the
            attack sign of each team in each period of basketball match {pf(BB, "match.match_id")}, the first frame of
            its possession in feet and in metres, and the pitch and the signs of football match{" "}
            {pf(FB, "match.match_id")}. It needs nothing else: no Track Lab code and no intermediate tables.
          </p>
          <ol>
            <li>
              Clone <code>https://github.com/SkillCorner/opendata-basketball</code> with Git LFS, which holds the
              tracking files, at <code>4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66</code>, and{" "}
              <code>https://github.com/SkillCorner/opendata</code> at <code>4340d274572876239c154c90bc507a9b3250a656</code>,
              side by side in one folder.
            </li>
            <li>Open a terminal in that folder.</li>
            <li>
              Save the query as <code>coordinates.sql</code> and run <code>duckdb &lt; coordinates.sql</code>.
            </li>
          </ol>
          <p>
            In the first result, team {pf(BB, "team_in_possession")} comes back with the sign{" "}
            {pf(BB, "attack_sign")} in the first period, the sign of the possession in the first figure. The second
            result&apos;s metres are that possession&apos;s first frame, every entity to the centimetre. The third gives
            team {pf(FB, "team_in_possession")} the sign {pf(FB, "attack_sign")} in the first period, on a pitch of{" "}
            {pf(FB, "surface.length_m")} by {pf(FB, "surface.width_m")}&nbsp;m. It was checked that way with DuckDB{" "}
            <code>1.5.5</code>.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="mathworld-affine" full /> and <Cite id="mathworld-rotation" full />: affine maps, and why a
              determinant tells a turn from a mirror.
            </li>
            <li>
              <Cite id="nist-811-b8" full />: the exact factors between customary units and the SI.
            </li>
            <li>
              <Cite id="skillcorner-bb-coords" full />, <Cite id="skillcorner-bb-lefthoop" full /> and{" "}
              <Cite id="skillcorner-fb-coords" full />: the providers&apos; own conventions.
            </li>
            <li>
              <a href="/engineering/quality">/engineering/quality</a>: the clock check behind the first columns of the table, beside the other
              checks of the bundles.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures figures={F} />
    </main>
  );
}
