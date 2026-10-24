import type { ReactNode } from "react";
import { REBOUND, reboundFig, reboundFigure } from "../../../lib/learn/rebound-data";
import { raceAt, reboundFigures, type ReboundFigures } from "../../../lib/learn/rebound-figures";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { ExposeFigures } from "./ExposeFigures";
import { PerMatch } from "./PerMatch";
import { RaceFigure } from "./RaceFigure";
import { ReactionPlot } from "./ReactionPlot";

// Lesson 4. No figure is typed: `r(path)` prints a value of rebound.json and `l(key)` one of
// `reboundFigures`, each as a `data-fig` the e2e compares with its source.
const F = reboundFigures(REBOUND);
const EX = REBOUND.example;
const l = (key: keyof ReboundFigures) => <Fig name={`learn.${key}`}>{String(F[key])}</Fig>;
const r = (path: string) => <Fig name={`rebound.${path}`}>{String(reboundFigure(REBOUND, `rebound.${path}`))}</Fig>;
const REPRO = EX.match_id;
const m = (field: string) => <Fig name={reboundFig(REPRO, field)}>{String(reboundFigure(REBOUND, reboundFig(REPRO, field)))}</Fig>;
const NATIVE = REPRO.replace(/^bb:/, "");

// A player of the example as the text names them: the shirt from the file, then the side;
// `Who` opens a sentence.
const side = (i: number) => (EX.players[i].team === "defending" ? "defence" : "attack");
const who = (i: number) => (
  <>
    number {r(`example.players.${i}.jersey`)} of the {side(i)}
  </>
);
const Who = (i: number) => (
  <>
    Number {r(`example.players.${i}.jersey`)} of the {side(i)}
  </>
);
const AT = raceAt(REBOUND, REBOUND.reaction_s, REBOUND.top_speed);
const SECOND = AT.times.map((t, i) => ({ t, i })).sort((a, b) => a.t - b.t)[1].i;

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
// Vectors in bold, as the Unicode mathematical bold letters.
const BOLD: Record<string, string> = { p: "𝐩", v: "𝐯", r: "𝐫" };
const vec = (x: string, i?: string) => {
  const bold = <mi>{BOLD[x]}</mi>;
  return i ? (
    <msub>
      {bold}
      <mi>{i}</mi>
    </msub>
  ) : (
    bold
  );
};
const norm = (inner: ReactNode) => (
  <>
    <mo>|</mo>
    {inner}
    <mo>|</mo>
  </>
);

export function Lesson({ sql }: { sql: string }) {
  return (
    <main className="page lesson learn-rebound">
      <LessonHead n={4} title="Who gets to the rebound first?" level="Intermediate">
        <p className="lede">
          When a shot misses, ten players go for the ball. Freeze them at the end of the shot, give each a reaction time and a
          top speed, and ask who would be first to the place where the rebounder was standing when he took it. That player is
          the rebounder in {l("model_lo")} to {l("model_hi")}&nbsp;% of rebounds, match by match. The player standing nearest
          to that place, with no model at all, is the rebounder in {l("near_lo")} to {l("near_hi")}&nbsp;%.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            SkillCorner&apos;s basketball events list every rebound with the player who took it and where. The provider defines
            that location as the <Quote id="skillcorner-rebound-location" /> (<Cite id="skillcorner-rebound-location" />). Every
            shot also carries the frame at which it ended, <Quote id="skillcorner-shot-end" /> (
            <Cite id="skillcorner-shot-end" />
            ). Between those two moments the ball comes off the rim and the players move.
          </p>
          <p>
            Freeze the tracking at the shot&apos;s last frame. Each player has a position and, from the frames either side, a
            velocity: the central difference of the <a href="/learn/speed">second lesson</a>. Can those two quantities say who
            will reach the ball first? And is a model of running worth more than the simplest rule there is, that the player
            standing nearest gets there first? This lesson builds the model, sets it beside that rule on one rebound, then counts
            both over every rebound of the ten matches.
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">Time to arrive</h2>
          <p>
            William Spearman&apos;s model of who wins the ball (<Cite id="spearman-2018" />) starts from a time to arrive: how
            long a player needs to reach a point on the floor, given where they are and how they are already moving. Laurie
            Shaw&apos;s public implementation reduces it to two phases. Its comment reads{" "}
            <Quote id="shaw-tti" /> (<Cite id="shaw-tti" />), after which the player covers the rest at top speed. For player{" "}
            <M><mi>i</mi></M> at <M>{vec("p", "i")}</M> with velocity <M>{vec("v", "i")}</M>, a target <M>{vec("r")}</M>, a
            reaction time <M><mi>τ</mi></M> and a top speed <M>{sub("v", <mi>max</mi>)}</M>:
          </p>
          <Formula label="The time to arrive of player i">
            <mrow>
              {sub("T", <mi>i</mi>)}
              <mo>=</mo>
              <mi>τ</mi>
              <mo>+</mo>
              {frac(
                norm(
                  <>
                    {vec("r")}
                    <mo>−</mo>
                    <mo>(</mo>
                    {vec("p", "i")}
                    <mo>+</mo>
                    {vec("v", "i")}
                    <mi>τ</mi>
                    <mo>)</mo>
                  </>,
                ),
                sub("v", <mi>max</mi>),
              )}
            </mrow>
          </Formula>
          <p>
            Shaw sets the reaction time at <Quote id="shaw-reaction" /> (<Cite id="shaw-reaction" />) and the top speed at{" "}
            <Quote id="shaw-top-speed" /> (<Cite id="shaw-top-speed" />), the top speed Spearman chose as well. This lesson
            keeps both, {r("reaction_s")}&nbsp;s and {r("top_speed")}&nbsp;m/s, and does not fit them to basketball.
          </p>
          <p>
            Now read the formula again with every player sharing one reaction time and one top speed. Adding the same{" "}
            <M><mi>τ</mi></M> to every time and dividing every remaining distance by the same{" "}
            <M>{sub("v", <mi>max</mi>)}</M> cannot change their order. So the top speed moves every time and never changes who
            is first. And with no reaction time the formula is a distance over a speed, so the model&apos;s first is the nearest
            player. Everything the model adds to the nearest rule comes from one term, <M>{vec("v", "i")}<mi>τ</mi></M>: how
            far the reaction time carries each player before they can turn toward the ball.
          </p>

          <h3>How sure is the first?</h3>
          <p>
            A time to arrive is an estimate. Players are not equally quick, they jump, they get in each other&apos;s way.
            Spearman models the difference between the expected and the actual arrival with a logistic distribution, and says
            why: <Quote id="spearman-2018" /> (<Cite id="spearman-2018" />). The chance that player <M><mi>i</mi></M> has
            arrived by time <M><mi>t</mi></M> is
          </p>
          <Formula label="The chance that player i has arrived by time t">
            <mrow>
              {sub("F", <mi>i</mi>)}
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <mo>=</mo>
              {frac(
                <mn>1</mn>,
                <>
                  <mn>1</mn>
                  <mo>+</mo>
                  <mi>exp</mi>
                  <mo>(</mo>
                  <mo>−</mo>
                  {frac(
                    <>
                      <mi>π</mi>
                      <mo>(</mo>
                      <mi>t</mi>
                      <mo>−</mo>
                      {sub("T", <mi>i</mi>)}
                      <mo>)</mo>
                    </>,
                    <>
                      <msqrt>
                        <mn>3</mn>
                      </msqrt>
                      <mi>s</mi>
                    </>,
                  )}
                  <mo>)</mo>
                </>,
              )}
            </mrow>
          </Formula>
          <p>
            where <M><mi>s</mi></M> is the standard deviation of the arrival time. Spearman fitted it at {r("spread_s")}
            &nbsp;s, the parameter his first table describes as <Quote id="spearman-2018-table" /> (
            <Cite id="spearman-2018-table" />
            ). Shaw&apos;s code uses another value, <Quote id="shaw-sigma" /> (<Cite id="shaw-sigma" />); this lesson keeps
            Spearman&apos;s own. If the arrivals are independent, the chance that <M><mi>i</mi></M> is first is the chance of arriving at some{" "}
            <M><mi>t</mi></M> while nobody else has:
          </p>
          <Formula label="The chance that player i arrives first">
            <mrow>
              {sub("P", <mi>i</mi>)}
              <mo>=</mo>
              <mo>∫</mo>
              {sub("F′", <mi>i</mi>)}
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <msub>
                <mo>∏</mo>
                <mrow>
                  <mi>j</mi>
                  <mo>≠</mo>
                  <mi>i</mi>
                </mrow>
              </msub>
              <mo>(</mo>
              <mn>1</mn>
              <mo>−</mo>
              {sub("F", <mi>j</mi>)}
              <mo>(</mo>
              <mi>t</mi>
              <mo>)</mo>
              <mo>)</mo>
              <mspace width="0.2em" />
              <mi>d</mi>
              <mi>t</mi>
            </mrow>
          </Formula>
          <p>
            The page works the integral out on a fine grid, the pipeline on the same one, and the chances add up to one. Two
            players a few hundredths of a second apart share the chance almost evenly; one player is nearly sure only when the
            gap is several times <M><mi>s</mi></M>.
          </p>
        </section>

        <section aria-labelledby="example-h">
          <h2 id="example-h">One rebound</h2>
          <p>
            The example is chosen by a rule: the first rebound of match {r("example.match_id")} in which the two rules name
            different players. That is the match the query at the end is written for. At the end of the shot,{" "}
            {who(EX.nearest)} stands nearest to the spot, {l("ex_near_dist")}&nbsp;m away. {Who(EX.rebounder)} stands{" "}
            {l("ex_reb_dist")}&nbsp;m away but is already moving, at {l("ex_reb_speed")}&nbsp;m/s, and the reaction time carries
            him {l("ex_reb_carry")}&nbsp;m along.
          </p>
          <RaceFigure file={REBOUND} />
          <p>
            With the sources&apos; values the model puts {who(EX.model)} first, at {l("ex_first_time")}&nbsp;s, then{" "}
            {who(SECOND)} at {l("ex_second_time")}&nbsp;s and {who(EX.nearest)} at {l("ex_near_time")}&nbsp;s. The rebound was
            taken {r("example.wait_s")}&nbsp;s after the shot ended, by {who(EX.rebounder)}. On this rebound the model names the
            player who took it and the nearest rule does not.
          </p>
          <p>
            The margins are thin. The first two are {l("ex_gap_ms")}&nbsp;ms apart, a small fraction of <M><mi>s</mi></M>, and
            their chances of being first are {l("ex_first_chance")} and {l("ex_second_chance")}&nbsp;%, with{" "}
            {l("ex_near_chance")}&nbsp;% for the nearest player. The model&apos;s first is a favourite, not a certainty.
          </p>
          <p>
            Now use the controls. Slide the reaction time down: below {l("ex_switch_reaction")}&nbsp;s the model&apos;s first is
            the nearest player again, and at zero the two rules agree by construction. Move the top speed instead: every time
            changes, the chances change with them, and the first stays where it was.
          </p>
        </section>

        <section aria-labelledby="matches-h">
          <h2 id="matches-h">From one rebound to ten matches</h2>
          <p>
            The pipeline ran the same race on every rebound it could. Of the {l("rebounds")} rebounds in the files,{" "}
            {l("raced")} pass every rule of selection listed under Limitations, between {l("n_lo")} and {l("n_hi")} per match.
            Each row of the table is one match.
          </p>
          <PerMatch matches={REBOUND.matches} rate={F.rate} />
          <p>
            The model&apos;s first took the rebound in {l("model_lo")} to {l("model_hi")}&nbsp;% of them, match by match; the
            nearest player in {l("near_lo")} to {l("near_hi")}&nbsp;%. The model names the player who took it more often in{" "}
            {l("ahead")} of {l("matches")} matches, as often in {l("level")}, and in {l("behind")} matches less often. Match by match the
            difference is {l("diff_lo")} to {l("diff_hi")} rebounds. For scale, a name drawn at random from the {r("players")} on court would be
            right one time in {r("players")}.
          </p>
          <p>
            The two rules name the same player in {l("same_lo")} to {l("same_hi")}&nbsp;% of rebounds. Whatever separates them
            happens in the rest: rebounds where a player&apos;s movement at the end of the shot carries him past someone
            standing closer, or away from a spot he stood next to.
          </p>
          <p>
            The model also says how sure it is. Averaged over a match, the chance it gave its own first of being first is{" "}
            {l("conf_lo")} to {l("conf_hi")}&nbsp;%. In {l("conf_above")} of {l("matches")} matches that average is higher than
            the share of rebounds its first actually took. The lesson puts the two numbers side by side and leaves the
            difference open.
          </p>
          <ReactionPlot file={REBOUND} />
          <p>
            The reaction time was taken from the sources before looking at these rebounds. The plot shows what happens when it
            is not. Every line starts at the nearest rule, as the algebra says it must. The count of rebounds the model&apos;s
            first took is highest at reaction times between {l("peak_lo")} and {l("peak_hi")}&nbsp;s, depending on the match, and
            falls at long ones, where the model sends every player far along the way they were already going. Choosing the
            reaction time at a line&apos;s peak would fit the model to the very rebounds it is then scored on: the figure would
            rise and say less.
          </p>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            Times to arrive with a logistic spread are the building block of Spearman&apos;s model of who wins the ball, and of
            the many models of space and control that followed it. Whatever is built on them depends on how well they put players
            in order, so it is worth measuring that order directly, on events whose outcome is known.
          </p>
          <p>
            A model that needs velocities, a reaction time and a top speed should be set beside the rule that needs none, on the
            same rebounds, match by match, and reported with the size of the difference. Here the one term that separates them
            moves a handful of rebounds per match. The count does not show that the model reads the ball better than the
            nearest rule does: the place it races to is where the rebounder ended up, so the reaction term favours a player
            who was already heading for his final spot.
          </p>
          <p>
            A model&apos;s chances are forecasts, and forecasts can be checked the same way: on these files the chance the model
            gives its first and the share its first takes are two different numbers, and both belong in the report.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              The target is where the player who took the rebound stood when he took it, which is after the shot ended: the
              provider&apos;s dictionary says <Quote id="skillcorner-rebound-location" /> (
              <Cite id="skillcorner-rebound-location" />
              ). The race is run to a point known only afterwards, so the reaction
              term favours a player already moving towards his final spot, and the count cannot show that the model reads the
              ball better than the nearest rule. Where the ball came down, and when, is not modelled.
            </li>
            <li>
              One frame decides everything: positions and velocities at the end of the shot. What happens next, contact,
              jumping, players holding their ground against others, is not in the model, and neither is anyone&apos;s height.
            </li>
            <li>
              Every player shares one reaction time and one top speed, taken from work on soccer and not refitted here. The
              spread <M><mi>s</mi></M> is Spearman&apos;s fitted value, also from soccer.
            </li>
            <li>
              Velocities are the central difference of the frames either side of the shot&apos;s end, as in the second lesson.
              Positions are used as the file gives them, every row, with no filter on any flag.
            </li>
            <li>
              The chance of being first assumes the players&apos; arrivals are independent, which players who block each other
              are not.
            </li>
            <li>
              The selection. Of the {l("rebounds")} rebounds, {l("team_rebounds")} were team rebounds with no player,{" "}
              {l("not_field_goal")} followed a free throw and have no shot to freeze, {l("no_location")} have no location,{" "}
              {l("not_after")} are not later than their shot&apos;s last frame, and in {l("not_ten")} the frames around the end
              of the shot do not hold ten players. The rest, {l("raced")}, are the rebounds of the table.
            </li>
            <li>Basketball only.</li>
            <li>Why the model&apos;s stated chances and the share its first takes differ stays open.</li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>
              In the race, find the reaction time at which the model&apos;s first changes. Which player&apos;s line crosses whose?
            </li>
            <li>Push the top speed to either end. Which numbers in the table move, and which never do? Explain it with the formula.</li>
            <li>Press No reaction and compare the model&apos;s first with the nearest player.</li>
            <li>
              With pencil and paper: two players at the same distance from the spot, one standing, one already running toward
              it. Which does the model put first, for any reaction time? And if the runner is running away?
            </li>
            <li>
              Run the query below on another match: change the id in every file name and compare the result with that
              match&apos;s row in the table.
            </li>
          </ul>
        </section>

        <Reproduce sql={sql}>
          <p>
            The query is the race of the table in DuckDB, written for the public files of match {r("example.match_id")}: the
            events file, read once for the rebounds and once for the shots, and the tracking file. It needs nothing else: no
            Track Lab code and no intermediate tables.
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
              Save the query as <code>rebound.sql</code> and run <code>duckdb &lt; rebound.sql</code>.
            </li>
          </ol>
          <p>
            It returns {m("n")} rebounds, {m("model")} where the model&apos;s first took the rebound and {m("nearest")} where the
            nearest player did, that match&apos;s row in the table above. The same query, with only the id changed, gives those
            three counts for every row; it was checked that way with DuckDB <code>1.5.5</code>.
          </p>
        </Reproduce>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="spearman-2018" full />: the time to arrive, its logistic spread and the model of control built on them.
            </li>
            <li>
              <Cite id="shaw-tti" full />: a short, readable implementation of the same model, with every parameter in one
              place.
            </li>
            <li>
              <Cite id="skillcorner-rebound-location" full />: the provider&apos;s definitions of every field of a rebound.
            </li>
            <li>
              <a href="/learn/speed">Where does the provider&apos;s speed come from?</a>, the second lesson, for the central
              difference that gives every velocity here.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures file={REBOUND} />
    </main>
  );
}
