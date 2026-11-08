import type { ReactNode } from "react";
import { CLIPS, FACING, publishedFigure } from "../../../lib/learn/facing-data";
import { facingFigures } from "../../../lib/learn/facing-figures";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { Compass } from "./Compass";
import { ExposeFigures } from "./ExposeFigures";
import { PerPlayer } from "./PerPlayer";

// Lesson 11. No figure is typed: `f(name)` prints a value of a published file, named
// "<file under public/data>:<dotted path>", and `l(key)` one of `facingFigures`, each as a
// `data-fig` the e2e compares with its source.
const F = facingFigures(FACING);
const get = (root: unknown, path: string): unknown =>
  path.split(".").reduce<unknown>((at, key) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[key] : undefined), root);
const l = (key: string) => <Fig name={`learn.${key}`}>{String(get(F, key))}</Fig>;
const f = (name: string) => <Fig name={name}>{String(publishedFigure(name))}</Fig>;
const p = (path: string) => f(`pose.json:${path}`);

const [A, B] = FACING;
const ca = (path: string) => f(`${A.file}:${path}`);
const cb = (path: string) => f(`${B.file}:${path}`);
const la = (key: string) => l(`hook.${A.match_id}.${key}`);
const lb = (key: string) => l(`hook.${B.match_id}.${key}`);
const qa = (key: string) => l(`clip.${A.match_id}.${key}`);
const qb = (key: string) => l(`clip.${B.match_id}.${key}`);
const ROWS = Object.fromEntries(FACING.map((c) => [String(c.match_id), F.players[c.match_id]]));
const HOOKS = Object.fromEntries(FACING.map((c) => [String(c.match_id), c.hook.index]));
const DETECTED_ONLY = CLIPS[A.file].limits.find((x) => x.id === "detected_only")?.text ?? "";

const sub = (x: string, i: ReactNode) => (
  <msub>
    <mi>{x}</mi>
    <mrow>{i}</mrow>
  </msub>
);
const bold = (x: string) => <mi>{x}</mi>;
const bsub = (x: string, i: ReactNode) => (
  <msub>
    {bold(x)}
    <mrow>{i}</mrow>
  </msub>
);
const frac = (num: ReactNode, den: ReactNode) => (
  <mfrac>
    <mrow>{num}</mrow>
    <mrow>{den}</mrow>
  </mfrac>
);
const tuple = (a: ReactNode, b: ReactNode) => (
  <mrow>
    <mo>(</mo>
    {a}
    <mo>,</mo>
    {b}
    <mo>)</mo>
  </mrow>
);
const atan2 = (y: ReactNode, x: ReactNode) => (
  <mrow>
    <mi>atan2</mi>
    {tuple(y, x)}
  </mrow>
);
const kpm = (sign: string) => (
  <mrow>
    <mi>k</mi>
    <mo>{sign}</mo>
    <mn>1</mn>
  </mrow>
);

function ClipText({ c, q }: { c: (path: string) => ReactNode; q: (key: string) => ReactNode }) {
  return (
    <>
      In the clip of match {c("match_id")}, {q("players")} players have at least {l("min_frames")} frames that count. Their medians run
      from {q("median_lo")} to {q("median_hi")}°, their circular variances from {q("var_lo")} to {q("var_hi")}, and the share of
      frames side on or further from {q("off_lo")} to {q("off_hi")}&nbsp;%. {q("forward")} of the {q("players")} keep the median under{" "}
      {l("side_deg")}°; the widest is number {q("widest_number")} of team {q("widest_team")}, at {q("widest_median")}°.
    </>
  );
}

export function Lesson({ script }: { script: string }) {
  return (
    <main className="page lesson learn-facing">
      <LessonHead
        n={11}
        title="Which way is a player facing?"
        level="Advanced"
        result={[
          { label: "Chest against run, median angle, per player, one clip", values: [F.clip[A.match_id].median_lo, F.clip[A.match_id].median_hi], unit: "°" },
          { label: "Frames side on or further, per player, one clip", values: [F.clip[A.match_id].off_lo, F.clip[A.match_id].off_hi], unit: "%" },
        ]}
      >
        <p className="lede">
          Body pose puts a skeleton on a player {ca("fps")} times a second. Two of its joints, the shoulders, draw a line across
          the chest, and a third, the nose, says which side of that line is the front. This lesson turns the three into a
          direction, sets it against the direction the player is moving in, and shows what it takes to average an angle.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            A player does not always look where they run. A defender backs off facing the ball, a forward checks over a shoulder,
            and a winger on the overlap runs with the chest half turned to the pitch. Tracking positions alone cannot see any of
            that: a dot has no front. Body pose has one. The provider&apos;s README lists the joints it places, beginning with the
            ones this lesson needs: <Quote id="skillcorner-bodypose-joints" /> (<Cite id="skillcorner-bodypose-joints" />).
          </p>
          <p>
            On the two clips <a href="/tracking/pose">/tracking/pose</a> publishes, the fifth lesson counted steps from the ankles. Here the question
            is which way each player faces while running, and how far that is from the way they are going. Two smaller questions
            sit underneath. How is a direction read from three points? And how are angles averaged, when two angles either side of
            straight back have an arithmetic mean that points straight ahead?
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">A direction as an angle</h2>
          <p>
            Take the two shoulders in one frame, both as the clip gives them, offsets from the player&apos;s own position, so where the
            player stands drops out. The line from the right shoulder to the left is a vector:
          </p>
          <Formula label="The shoulder line, right to left">
            <mrow>
              {bold("s")}
              <mo>=</mo>
              {bsub("p", <mi>L</mi>)}
              <mo>−</mo>
              {bsub("p", <mi>R</mi>)}
            </mrow>
          </Formula>
          <p>
            A line has two normals, one on each side, and a chest faces along one of them. The nose decides which: of the two
            normals, the facing is the one that points to the same side as the nose, measured from the midpoint{" "}
            <M>{bold("m")}</M> between the shoulders. Its angle from the pitch&apos;s x axis is the facing <M><mi>φ</mi></M>:
          </p>
          <Formula label="The facing: the normal to the shoulder line on the nose's side">
            <mrow>
              {bold("n")}
              <mo>=</mo>
              {tuple(sub("s", <mi>y</mi>), <mrow><mo>−</mo>{sub("s", <mi>x</mi>)}</mrow>)}
              <mo>,</mo>
              <mspace width="1em" />
              <mi>φ</mi>
              <mo>=</mo>
              {atan2(sub("n", <mi>y</mi>), sub("n", <mi>x</mi>))}
              <mspace width="0.5em" />
              <mtext>if</mtext>
              <mspace width="0.5em" />
              {bold("n")}
              <mo>·</mo>
              <mo>(</mo>
              {bsub("p", <mi>N</mi>)}
              <mo>−</mo>
              {bold("m")}
              <mo>)</mo>
              <mo>&gt;</mo>
              <mn>0</mn>
              <mo>,</mo>
              <mspace width="0.5em" />
              <mtext>else of</mtext>
              <mspace width="0.5em" />
              <mo>−</mo>
              {bold("n")}
            </mrow>
          </Formula>
          <p>
            Nothing here depends on which shoulder the provider calls the left one. Swap the two and <M>{bold("s")}</M> flips, both
            normals flip with it, and the nose picks the same side as before. The blind spot the fifth lesson had to list, a left
            and right that might be mislabelled, does not reach this angle. A frame where the nose lies exactly on the shoulder
            line, or the shoulders coincide, gives no facing and is left out.
          </p>
          <p>
            The direction of travel comes from the second lesson&apos;s central difference: the player&apos;s position in the frame
            after minus the position in the frame before. For a direction the frame step cancels; for the speed it does not, and the
            lesson needs the speed too:
          </p>
          <Formula label="The heading and the speed at frame k from the frames either side">
            <mrow>
              {sub("θ", <mi>k</mi>)}
              <mo>=</mo>
              {atan2(
                <mrow>
                  {sub("y", kpm("+"))}
                  <mo>−</mo>
                  {sub("y", kpm("−"))}
                </mrow>,
                <mrow>
                  {sub("x", kpm("+"))}
                  <mo>−</mo>
                  {sub("x", kpm("−"))}
                </mrow>,
              )}
              <mo>,</mo>
              <mspace width="1em" />
              {sub("v", <mi>k</mi>)}
              <mo>=</mo>
              {frac(
                <mrow>
                  <mo>|</mo>
                  {bsub("p", kpm("+"))}
                  <mo>−</mo>
                  {bsub("p", kpm("−"))}
                  <mo>|</mo>
                </mrow>,
                <mrow>
                  <mn>2</mn>
                  <mi>Δ</mi>
                  <mi>t</mi>
                </mrow>,
              )}
            </mrow>
          </Formula>
          <p>
            The speed matters because the positions in the pose file are not measured at its frame rate:{" "}
            <Quote id="skillcorner-bodypose-interpolated" /> (<Cite id="skillcorner-bodypose-interpolated" />). Over the{" "}
            {l("span_ms")}&nbsp;ms between the two neighbours, a player who is nearly still moves less than the positions wobble, and
            the heading of such a frame is mostly noise. So a frame counts only when the speed over its two neighbours is above{" "}
            {l("min_speed")}&nbsp;m/s, and a player counts only with at least {l("min_frames")} such frames. Both floors are this
            lesson&apos;s, not the provider&apos;s.
          </p>
          <p>
            The relative angle is the facing minus the heading, brought back onto the circle so that it lies within a half turn of
            zero either way:
          </p>
          <Formula label="The relative angle, in the half turn either side of zero">
            <mrow>
              <mi>Δ</mi>
              <mo>=</mo>
              <mn>180</mn>
              <mo>−</mo>
              <mo>(</mo>
              <mo>(</mo>
              <mn>180</mn>
              <mo>−</mo>
              <mo>(</mo>
              <mi>φ</mi>
              <mo>−</mo>
              <mi>θ</mi>
              <mo>)</mo>
              <mo>)</mo>
              <mspace width="0.3em" />
              <mi>mod</mi>
              <mspace width="0.3em" />
              <mn>360</mn>
              <mo>)</mo>
            </mrow>
          </Formula>
          <p>
            Zero is a chest square to the run; a half turn either way is the back to it. The sign says which side the chest is
            turned to, in the pitch&apos;s own axes.
          </p>
          <p>
            Now the mean. Two frames with the chest at {l("demo_a")}° and {l("demo_b")}° both face nearly backwards, and their
            arithmetic mean is {l("demo_arith")}°: straight ahead. The circle has no place for an arithmetic mean. SciPy&apos;s
            reference, which many analysts reach for first, defines the alternative plainly: <Quote id="scipy-circmean" /> (
            <Cite id="scipy-circmean" />). Each angle becomes a unit vector, the vectors are averaged, and the mean angle is the
            direction of that average:
          </p>
          <Formula label="The mean resultant vector of n angles, its argument and its length">
            <mrow>
              {tuple(<mi>C</mi>, <mi>S</mi>)}
              <mo>=</mo>
              {frac(<mn>1</mn>, <mi>n</mi>)}
              <msub>
                <mo>∑</mo>
                <mi>i</mi>
              </msub>
              {tuple(
                <mrow>
                  <mi>cos</mi>
                  {sub("Δ", <mi>i</mi>)}
                </mrow>,
                <mrow>
                  <mi>sin</mi>
                  {sub("Δ", <mi>i</mi>)}
                </mrow>,
              )}
              <mo>,</mo>
              <mspace width="1em" />
              <mover>
                <mi>Δ</mi>
                <mo>¯</mo>
              </mover>
              <mo>=</mo>
              {atan2(<mi>S</mi>, <mi>C</mi>)}
              <mo>,</mo>
              <mspace width="1em" />
              <mi>R</mi>
              <mo>=</mo>
              <msqrt>
                <msup>
                  <mi>C</mi>
                  <mn>2</mn>
                </msup>
                <mo>+</mo>
                <msup>
                  <mi>S</mi>
                  <mn>2</mn>
                </msup>
              </msqrt>
            </mrow>
          </Formula>
          <p>
            The length of the average carries the spread. Unit vectors that all point the same way average to a vector of length
            one; vectors spread evenly round the circle average to nothing. SciPy names it in the entry for the circular variance,
            where the quantity under the bars <Quote id="scipy-circvar" /> (<Cite id="scipy-circvar" />), and the circular variance
            is one minus it. For the two angles above the circular mean is {l("demo_circ")}° and the length {l("demo_resultant")}:
            nearly backwards, nearly agreed. Alongside the mean, the lesson reports the median of the angle&apos;s size, which needs
            no circle at all, and the share of frames past {l("side_deg")}° either way, side on or further, and past {l("back_deg")}
            °, the back to the run.
          </p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">One player</h2>
          <p>
            The figure takes the player whose window the fifth lesson read, number {ca(`players.${A.hook.index}.number`)} of team{" "}
            {ca(`players.${A.hook.index}.team_id`)} in the clip of match {ca("match_id")}: {l("clip_frames")} frames,{" "}
            {l("clip_seconds")}&nbsp;s of video. {la("frames")} of them count, at {la("speed_lo")} to {la("speed_hi")}&nbsp;m/s. In
            the first, frame {la("first_frame_id")}, the chest faces {la("first_facing")}° while the player moves at{" "}
            {la("first_heading")}°: a relative angle of {la("first_relative")}°.
          </p>
          <Compass clips={FACING} />
          <p>
            Over the {la("frames")} frames the median of the angle&apos;s size is {la("median_abs")}° and the circular mean{" "}
            {la("circ_mean")}°, with a mean resultant length of {la("resultant")}, a circular variance of {la("circ_var")}. The chest
            is side on or further in {la("off_pct")}&nbsp;% of the frames and turned to the back in {la("back_pct")}&nbsp;%; the
            widest frame is {la("widest_frame_id")}, at {la("widest_relative")}°. A mean well away from zero with a length near one
            is a player who ran with the chest held to one side for most of the clip. The lesson says that much and no more: the
            clip is {l("clip_seconds")} seconds around one run, chosen by the fifth lesson&apos;s rule for its cadence, not for this.
          </p>
          <p>
            The other clip, from match {cb("match_id")}, holds number {cb(`players.${B.hook.index}.number`)} of team{" "}
            {cb(`players.${B.hook.index}.team_id`)}: {lb("frames")} frames count, a median of {lb("median_abs")}°, a circular mean of{" "}
            {lb("circ_mean")}° with length {lb("resultant")}, and {lb("off_pct")}&nbsp;% of frames side on or further. Switch the
            figure to it and the rose changes shape.
          </p>
        </section>

        <section aria-labelledby="players-h">
          <h2 id="players-h">From one player to every player</h2>
          <p>
            Every player in each clip is read the same way, and a row is kept for each with at least {l("min_frames")} frames that
            count. The table gives the row; the plot above it draws the median.
          </p>
          <PerPlayer rows={ROWS} hooks={HOOKS} />
          <p>
            <ClipText c={ca} q={qa} /> <ClipText c={cb} q={qb} />
          </p>
          <p>
            Most players, most of the time, run with the chest within a quarter turn of the way they are going; a few keep it
            further round for much of a clip. Whether that is a role, a moment or a limit of the joints, two clips of a few seconds
            cannot say, and the lesson does not ask.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            A direction is a quantity on a circle, and the circle closes. Any figure built from directions, where a player faces,
            where a pass went, which way a team moves the ball, inherits that: an arithmetic mean of angles is wrong without warning,
            and a standard deviation of them is wrong in the same silent way. The mean resultant vector gives both a mean and a
            measure of agreement in one step, and its length is the number to print beside any mean angle.
          </p>
          <p>
            The facing also shows what pose adds to tracking. From positions alone a player is a dot with a velocity; from three
            joints the dot gets a front, and the difference between the two directions is a new descriptor at every frame. It is
            built here from the fewest joints that give it, with every rule written down, so that a reader who wants the hips or the
            eyes instead can change one line and see what moves.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              The heading is read from positions that are not pose measurements: <Quote id="skillcorner-bodypose-interpolated" /> (
              <Cite id="skillcorner-bodypose-interpolated" />). The floor on speed limits the noise that lets in; it does not remove it.
            </li>
            <li>
              The facing and the heading come from two systems: <Quote id="skillcorner-bodypose-separate" /> (
              <Cite id="skillcorner-bodypose-separate" />). Part of any relative angle may be a disagreement between them.
            </li>
            <li>
              Body pose exists only where the provider found the player: <q>{DETECTED_ONLY}</q> (<Cite id="skillcorner-bodypose" />
              ). A frame without a skeleton drops out, and the lesson does not ask what it leaves out.
            </li>
            <li>
              Three joints, written to the centimetre in the clip, with no predicted error carried through. The fifth lesson shows
              how to carry it; here the hips, the eyes or the feet would each give another facing, and none is tried.
            </li>
            <li>
              Two clips of {l("clip_frames")} frames, two matches, and the players chosen by the clips, not by this lesson. The
              numbers are those players in those seconds.
            </li>
            <li>The joints&apos; third coordinate is not used; the facing is a direction on the pitch, with no tilt.</li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>
              Slide the frame to the one the text calls the widest. Where is the nose, and where is the heading arrow? Then go to a
              frame where the arc nearly vanishes.
            </li>
            <li>Switch the compass to the other clip. Is the rose turned to the same side?</li>
            <li>
              In the second figure, find the player with the largest circular variance. Is their median also the largest? What
              would make the two disagree?
            </li>
            <li>
              With pencil and paper: three frames face a quarter turn to the left, straight ahead and a quarter turn to the right.
              What is the mean resultant length, and what does it say about the mean?
            </li>
            <li>Run the script below with a player index as its second argument, and compare with that player&apos;s row.</li>
          </ul>
        </section>

        <Reproduce sql={script} browser="facing">
          <p>
            The script reads the clip /tracking/pose already publishes and needs nothing but Python&apos;s standard library: no Track Lab
            code, no numpy, and the provider&apos;s match files only through the clip.
          </p>
          <ol>
            <li>
              Save it as <code>facing.py</code>.
            </li>
            <li>
              Run <code>python facing.py</code>. It downloads{" "}
              <code>https://tracklab-sable.vercel.app/data/pose/hook_1925299.json</code>, {p("clips.0.bytes")} bytes with checksum{" "}
              <code>{p("clips.0.sha256")}</code>. Pass a saved copy of that file, or of the other clip, as its first argument to work
              offline, and a player&apos;s index in the clip as its second to read another player.
            </li>
          </ol>
          <p>
            For the window&apos;s player it prints {la("frames")} lines, one per frame that counts, each with the speed and the three
            angles to three decimals; the first is frame {la("first_frame_id")} with a facing of {la("first_facing")}°, a heading of{" "}
            {la("first_heading")}° and a relative angle of {la("first_relative")}°. Then the summary: a median of {la("median_abs")}°, a
            circular mean of {la("circ_mean")}°, a mean resultant length of {la("resultant")}, a circular variance of {la("circ_var")}{" "}
            and {la("off_pct")}&nbsp;% of frames side on or further. Those are this page&apos;s figures, because the script reads the
            same clip with the same steps.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="scipy-circmean" full /> and <Cite id="scipy-circvar" full />: the mean resultant vector, its argument and its
              length, as a library defines them.
            </li>
            <li>
              <Cite id="skillcorner-bodypose-joints" full />: the provider&apos;s description of the joints, their coordinates and their
              limits.
            </li>
            <li>
              <a href="/learn/speed">Where does the provider&apos;s speed come from?</a>, the second lesson, for the central difference,
              and <a href="/learn/cadence">How many steps per second?</a>, the fifth, for the same two clips read from the ankles.
            </li>
            <li>
              <a href="/tracking/pose">/tracking/pose</a>: the viewer and the protocol behind the clips.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures clips={FACING} />
    </main>
  );
}
