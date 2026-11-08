import type { ReactNode } from "react";
import { seasonLabel } from "../../../lib/euroleague/atlas";
import { EXPECTED, xpFigure, xpName } from "../../../lib/learn/expected-data";
import { lessonExpectedFigures } from "../../../lib/learn/expected-figures";
import { EUROLEAGUE, SITE, TAKEDOWN_CONTACT } from "../../../lib/sections";
import { Band } from "../../site/Band";
import { Cite, Quote } from "../Cite";
import { Fig } from "../Fig";
import { Formula, M } from "../Formula";
import { LessonHead } from "../LessonHead";
import { Limitations } from "../Limitations";
import { Reproduce } from "../Reproduce";
import { ExposeFigures } from "./ExposeFigures";
import { PerTeam } from "./PerTeam";
import { ZoneBars } from "./ZoneBars";

// Lesson 12 (task 117). No figure is typed: `x(season, path)` prints a value of
// expected-points.json (`xp.<season>.<path>`), `r(path)` one from the file's root, and `l(path)`
// one of `lessonExpectedFigures` (`learn.<path>`), each as a `data-fig` the e2e compares with its
// source. A season is named by its code in the file, printed as "2025-26" in a `data-season`.
const FILE = EXPECTED;
const F = lessonExpectedFigures(FILE);
const [S0, S1] = FILE.seasons;
const A = S0.season;
const B = S1.season;
const EX = F.ex.code;

const get = (root: unknown, path: string): unknown =>
  path.split(".").reduce<unknown>((at, key) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[key] : undefined), root);
const x = (season: string, path: string) => <Fig name={xpName(season, path)}>{String(xpFigure(FILE, xpName(season, path)))}</Fig>;
const r = (path: string) => <Fig name={`xp.${path}`}>{String(xpFigure(FILE, `xp.${path}`))}</Fig>;
const l = (path: string) => <Fig name={`learn.${path}`}>{String(get(F, path))}</Fig>;
const s = (season: string, key: string) => l(`season.${season}.${key}`);
const team = (path: string) => x(A, `teams.${EX}.${path}`);
const Season = ({ code }: { code: string }) => <span data-season={code}>{seasonLabel(code)}</span>;

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
const sum = (body: ReactNode) => (
  <>
    <msub>
      <mo>∑</mo>
      <mi>z</mi>
    </msub>
    {body}
  </>
);
const ebar = (
  <mover>
    <mi>e</mi>
    <mo>¯</mo>
  </mover>
);
const sumI = (body: ReactNode) => (
  <>
    <msub>
      <mo>∑</mo>
      <mi>i</mi>
    </msub>
    <mo>(</mo>
    {body}
    <mo>)</mo>
  </>
);
const ezi = (
  <msub>
    <mi>e</mi>
    <msub>
      <mi>z</mi>
      <mi>i</mi>
    </msub>
  </msub>
);
const tz = (
  <>
    <mi>t</mi>
    <mo>,</mo>
    <mi>z</mi>
  </>
);

export function Lesson({ sql }: { sql: string }) {
  return (
    <main className="page lesson learn-expected">
      <LessonHead
        n={12}
        title="How many points is a shot worth?"
        level="Foundations"
        result={[
          { label: `A two near the rim, points per shot, ${seasonLabel(A)}`, values: [S0.pps.rim] },
          { label: "A three", values: [S0.pps.three] },
          { label: "A two from further out", values: [S0.pps.mid] },
        ]}
      >
        <p className="lede">
          In the EuroLeague season that ended on {x(A, "cutoff")}, a two near the rim was worth {x(A, "pps.rim")} points per
          attempt, a three {x(A, "pps.three")} and a two from further out {x(A, "pps.mid")}. Where a team shoots from sets the
          points it can expect; how well it finishes from there does the rest. Expected points pull the two apart.
        </p>
      </LessonHead>
      <Band>
        <section aria-labelledby="question-h">
          <h2 id="question-h">The question</h2>
          <p>
            The EuroLeague&apos;s game feed records every field goal with the points it scored and a zone letter for where it was
            taken. This site keeps none of those shots. What it publishes are counts: by season, how many field goals the league
            and each team tried, made and scored in three classes of zone. A two in zone {r("rim_zones.0")}, {r("rim_zones.1")}{" "}
            or {r("rim_zones.2")}, the zones nearest the hoop, is a shot at the <em>rim</em>; any other two with a zone is{" "}
            <em>mid</em>-range; a three is a <em>three</em> wherever it was taken. The same counts draw the{" "}
            <a href="/euroleague">shot atlas</a>.
          </p>
          <p>
            How many points is an attempt from each class worth, and how much of what a team scores per shot comes from where it
            shoots rather than from how well?
          </p>
        </section>

        <section aria-labelledby="concept-h">
          <h2 id="concept-h">What an attempt is worth</h2>
          <p>
            An attempt scores its value or nothing. If the league made a share <M>{sub("p", <mi>z</mi>)}</M> of its attempts in
            a class <M><mi>z</mi></M>, each worth <M>{sub("v", <mi>z</mi>)}</M> points, an attempt there was worth, on average,
            its expected value, which <Quote id="mathworld-expectation" /> (<Cite id="mathworld-expectation" />
            ). Counted, it is the class&apos;s points over its attempts:
          </p>
          <Formula label="The points per attempt of a zone class">
            <mrow>
              {sub("e", <mi>z</mi>)}
              <mo>=</mo>
              {sub("v", <mi>z</mi>)}
              <mo>⁢</mo>
              {sub("p", <mi>z</mi>)}
              <mo>=</mo>
              {frac(sub("P", <mi>z</mi>), sub("n", <mi>z</mi>))}
            </mrow>
          </Formula>
          <p>
            In <Season code={A} /> the league tried {x(A, "league.rim.n")} twos at the rim and made {s(A, "pct.rim")}&nbsp;%,
            each worth {s(A, "value.rim")}: {x(A, "pps.rim")} points per attempt. From mid-range it made {s(A, "pct.mid")}
            &nbsp;% of {x(A, "league.mid.n")}, worth {s(A, "value.mid")}: {x(A, "pps.mid")}. From three it made{" "}
            {s(A, "pct.three")}&nbsp;% of {x(A, "league.three.n")}, worth {s(A, "value.three")}: {x(A, "pps.three")}. In{" "}
            <Season code={B} />, after {x(B, "games_played")} games, the three classes give {x(B, "pps.rim")},{" "}
            {x(B, "pps.mid")} and {x(B, "pps.three")}.
          </p>
          <p>
            The league&apos;s points per shot over the three classes is the mean of the <M>{sub("e", <mi>z</mi>)}</M>, each
            weighted by its attempts, which is all the points over all the attempts:
          </p>
          <Formula label="The league's points per shot, the attempt-weighted mean of the classes">
            <mrow>
              {ebar}
              <mo>=</mo>
              {frac(sum(<>{sub("n", <mi>z</mi>)}{sub("e", <mi>z</mi>)}</>), sum(sub("n", <mi>z</mi>)))}
              <mo>=</mo>
              {frac(sum(sub("P", <mi>z</mi>)), sum(sub("n", <mi>z</mi>)))}
            </mrow>
          </Formula>
          <p>
            It is {x(A, "mean")} in <Season code={A} /> and {x(B, "mean")} in <Season code={B} />. The plain mean of the three
            classes, as if each were tried as often, would be {s(A, "plain")} and {s(B, "plain")}: the weights are where the
            league shoots from. In the figure each class is a bar as wide as its share of the attempts.
          </p>
          <ZoneBars seasons={FILE.seasons} />
        </section>

        <section aria-labelledby="team-h">
          <h2 id="team-h">A team against the league</h2>
          <p>
            A team <M><mi>t</mi></M> takes its own mix of shots. Give each of its <M>{sub("n", tz)}</M> attempts in a class the
            league&apos;s value there, and the mean of those values over its attempts is its expected points per shot:
          </p>
          <Formula label="A team's expected points per shot">
            <mrow>
              {sub("x", <mi>t</mi>)}
              <mo>=</mo>
              {frac(sum(<>{sub("n", tz)}{sub("e", <mi>z</mi>)}</>), sum(sub("n", tz)))}
            </mrow>
          </Formula>
          <p>
            Its own points per shot, <M>{sub("p", <mi>t</mi>)}</M>, its points over its attempts, then differs from the
            league&apos;s by two parts that add up: what its mix alone was worth at the league&apos;s finishing, and what it scored
            beyond that from the same mix.
          </p>
          <Formula label="A team's points per shot against the league's: mix plus making">
            <mrow>
              {sub("p", <mi>t</mi>)}
              <mo>−</mo>
              {ebar}
              <mo>=</mo>
              <mo>(</mo>
              {sub("x", <mi>t</mi>)}
              <mo>−</mo>
              {ebar}
              <mo>)</mo>
              <mo>+</mo>
              <mo>(</mo>
              {sub("p", <mi>t</mi>)}
              <mo>−</mo>
              {sub("x", <mi>t</mi>)}
              <mo>)</mo>
            </mrow>
          </Formula>
          <p>
            The lesson calls the first part <em>mix</em> and the second <em>making</em>. Take the team with the most points per
            shot in <Season code={A} />, {team("name")}. It took {l("ex.share.rim")}&nbsp;% of its attempts at the rim,{" "}
            {l("ex.share.mid")}&nbsp;% from mid-range and {l("ex.share.three")}&nbsp;% from three. At the league&apos;s values
            those attempts were worth {team("xpps")} per shot, so its mix, {team("xpps")} minus {x(A, "mean")}, is{" "}
            {l("ex.mix")}. It scored {team("pps")}, so its making, {team("pps")} minus {team("xpps")}, is {l("ex.making")}.
            {F.ex.mix !== xpFigure(FILE, xpName(A, `teams.${EX}.mix`)) && (
              <>
                {" "}
                The table, which subtracts before it rounds, has its mix at {team("mix")}.
              </>
            )}
          </p>
        </section>

        <section aria-labelledby="teams-h">
          <h2 id="teams-h">Every team, both seasons</h2>
          <h3 id="teams-question-h">The question</h3>
          <p>
            The tables below split every team the same way. But a season is a sample: had a team taken the same kind of shots
            again, it would have made a few more or a few fewer, from a slightly different mix. Is a team&apos;s mix, or its
            making, more than that chance alone would give?
          </p>
          <h3 id="teams-method-h">The method</h3>
          <p>
            Both parts are means over the team&apos;s <M>{sub("n", <mi>t</mi>)}</M> attempts. An attempt <M><mi>i</mi></M>, in
            class <M>{sub("z", <mi>i</mi>)}</M> and scoring <M>{sub("y", <mi>i</mi>)}</M> points, adds to the mix the
            league&apos;s value of its class minus the league&apos;s points per shot, and to the making the points it scored minus
            that value:
          </p>
          <Formula label="Mix, a mean over the team's attempts">
            <mrow>
              {sub("x", <mi>t</mi>)}
              <mo>−</mo>
              {ebar}
              <mo>=</mo>
              {frac(<mn>1</mn>, sub("n", <mi>t</mi>))}
              {sumI(
                <>
                  {ezi}
                  <mo>−</mo>
                  {ebar}
                </>,
              )}
            </mrow>
          </Formula>
          <Formula label="Making, a mean over the team's attempts">
            <mrow>
              {sub("p", <mi>t</mi>)}
              <mo>−</mo>
              {sub("x", <mi>t</mi>)}
              <mo>=</mo>
              {frac(<mn>1</mn>, sub("n", <mi>t</mi>))}
              {sumI(
                <>
                  {sub("y", <mi>i</mi>)}
                  <mo>−</mo>
                  {ezi}
                </>,
              )}
            </mrow>
          </Formula>
          <p>
            If the attempts were independent draws, each from the team&apos;s own mix of classes and made at its own rate in the
            class, such a mean would vary from one season to another by its standard error: the spread <M><mi>s</mi></M> of what
            one attempt adds, over the square root of the attempts. The interval of each part is the part plus and minus{" "}
            {r("z")} standard errors; under that model, an interval built this way holds the team&apos;s underlying figure{" "}
            {l("level_pct")}&nbsp;% of the time:
          </p>
          <Formula label="The interval of mix or making">
            <mrow>
              <mi>m</mi>
              <mo>±</mo>
              <mi>z</mi>
              {frac(<mi>s</mi>, <msqrt>{sub("n", <mi>t</mi>)}</msqrt>)}
            </mrow>
          </Formula>
          <p>
            The counts are enough. In a class, every attempt adds the same to the mix, every make the same to the making and
            every miss the same, so the spread comes from the attempts and makes of each class; the query under Reproduce it
            computes it.
          </p>
          <h3 id="teams-result-h">The result</h3>
          <p>
            In <Season code={A} />, mix runs from {s(A, "mix_lo")} ({s(A, "mix_lo_code")}) to {s(A, "mix_hi")} (
            {s(A, "mix_hi_code")}), a range of {s(A, "mix_range")}; making runs from {s(A, "making_lo")} ({s(A, "making_lo_code")}
            ) to {s(A, "making_hi")} ({s(A, "making_hi_code")}), a range of {s(A, "making_range")}, {s(A, "ratio")} times as wide.{" "}
            {s(A, "making_pos")} of the {s(A, "teams")} teams scored more per shot than their mix was worth.
          </p>
          <p>
            The intervals turn that round. The interval of making excludes zero for {s(A, "excl_making")} of the{" "}
            {s(A, "teams")} teams; that of mix, for {s(A, "excl_mix")}. Making spreads the teams {s(A, "ratio")} times as wide as
            mix does, but its median interval is {s(A, "width_ratio")} times as wide as mix&apos;s: most teams&apos; making is
            within what a season of attempts varies by, and most teams&apos; mix is not.
          </p>
          <p>
            In <Season code={B} />, after {x(B, "games_played")} games, mix runs from {s(B, "mix_lo")} to {s(B, "mix_hi")} and
            making from {s(B, "making_lo")} to {s(B, "making_hi")}, {s(B, "ratio")} times as wide; {s(B, "making_pos")} of{" "}
            {s(B, "teams")} teams are above their mix. Its making intervals are {s(B, "width_ratio")} times as wide as its mix
            intervals, and {s(B, "excl_making")} making and {s(B, "excl_mix")} mix intervals exclude zero.
          </p>
          <PerTeam seasons={FILE.seasons} level={{ z: FILE.z, pct: F.level_pct }} />
          <h3 id="teams-limits-h">The limits</h3>
          <ul>
            <li>
              An interval that excludes zero reports a number, not a verdict. A making above zero is not better shooting and a
              mix below zero is not worse shot selection: the league&apos;s values price each class, and say nothing of the
              players, the plays or the defences behind a team&apos;s figure.
            </li>
            <li>
              With {s(A, "teams")} teams and intervals at {l("level_pct")}&nbsp;%, about {s(A, "chance")} would exclude zero by
              chance alone if no team differed from the league. The {s(A, "excl_making")} making intervals of <Season code={A} />{" "}
              that do are more than that, but the intervals cannot say which of them chance put there.
            </li>
            <li>
              The intervals take every attempt as independent, and where a team shoots from changes from game to game more than
              that allows (see the limitations below). Widened by the median factor found there, {s(A, "wide_mix")} mix intervals
              of <Season code={A} /> still exclude zero, and {s(B, "wide_mix")} of <Season code={B} />.
            </li>
            <li>
              The lesson stops at the split. Whether a team&apos;s shooters, the defences it met or chance explain its making, the
              counts cannot say, and the games of a season under way are fewer still.
            </li>
          </ul>
        </section>

        <section aria-labelledby="matters-h">
          <h2 id="matters-h">Why it matters</h2>
          <p>
            Points per shot answer two questions at once: are the shots good ones, and are they going in? A figure that does not
            split them cannot say which one moved. Expected points split them with nothing but counts: the league&apos;s points per
            attempt in each class, and how often the team tried each one.
          </p>
          <p>
            And the mean depends on its weights. The league&apos;s points per shot is not the mean of its three classes; it is
            their mean weighted by where the league shoots from, and a team&apos;s expected points are the same mean with the
            team&apos;s weights.
          </p>
        </section>

        <Limitations>
          <ul>
            <li>
              Field goals only. Free throws, those of a foul on a shot included, are in no figure, and neither are turnovers: this
              is points per field goal attempt, not per possession.
            </li>
            <li>
              Three classes are coarse. A corner three and one from the top of the arc are one class, and so are a dunk and a shot
              from the edge of the zones near the hoop; the hexagons of the <a href="/euroleague">shot atlas</a> show the spots.
            </li>
            <li>The league&apos;s values include the team&apos;s own attempts, and the intervals take them as fixed.</li>
            <li>
              The intervals take every attempt as independent. Resampling each team&apos;s whole games instead, from the shots of
              each game (which this site does not publish; seed {r("games_bootstrap.seed")}, {r("games_bootstrap.replicates")}{" "}
              draws), the mix intervals of <Season code={A} /> come out a median {x(A, "games_ratio.mix.median")} times as wide
              (from {x(A, "games_ratio.mix.min")} to {x(A, "games_ratio.mix.max")} by team): where a team shoots from changes from
              game to game more than independent attempts allow. The making intervals come out {x(A, "games_ratio.making.median")}{" "}
              times as wide (from {x(A, "games_ratio.making.min")} to {x(A, "games_ratio.making.max")}), so for making the model
              holds. In <Season code={B} />, on the few games played, the two medians are {x(B, "games_ratio.mix.median")} and{" "}
              {x(B, "games_ratio.making.median")}.
            </li>
            <li>
              Twos the feed gives no zone are in no class: {x(A, "league.unclassified")} in <Season code={A} /> and{" "}
              {x(B, "league.unclassified")} in <Season code={B} />.
            </li>
            <li>
              <Season code={B} /> counts the {x(B, "games_played")} games played up to {x(B, "cutoff")}.
            </li>
            <li>
              Only counts are published, and a class with fewer than {r("k")} attempts would be left out with its team; teams left
              out: {x(A, "teams_left_out")} in <Season code={A} />, {x(B, "teams_left_out")} in <Season code={B} />.
            </li>
          </ul>
        </Limitations>

        <section aria-labelledby="try-h">
          <h2 id="try-h">Try it yourself</h2>
          <ul>
            <li>
              With pencil and paper: what would a team score per shot if it took only threes and made them at the league&apos;s
              rate? And one with the league&apos;s mix that made every class at its own rate?
            </li>
            <li>In the tables, find the team with the largest making in the season under way. Where was it a season earlier?</li>
            <li>
              In the query below, replace the weighted mean by the plain mean of the three classes and see which rows stop
              matching the page.
            </li>
          </ul>
        </section>

        <Reproduce sql={sql} browser="expected-points">
          <p>
            Every figure of this lesson comes from one file of counts, the one this page reads. The query below rebuilds the
            tables&apos; rows from those counts in DuckDB, with no Track Lab code and nothing from the feed itself.
          </p>
          <ol>
            <li>
              Download <code>{`${SITE}/data/euroleague/expected-points.json`}</code>.
            </li>
            <li>
              Save the query as <code>expected-points.sql</code> in the same folder.
            </li>
            <li>
              Run <code>duckdb &lt; expected-points.sql</code> there.
            </li>
          </ol>
          <p>
            It returns one row per team and season, {l(`season.${A}.teams`)} for <Season code={A} /> and{" "}
            {l(`season.${B}.teams`)} for <Season code={B} />, with the four figures of the tables and the bounds of the two
            intervals: the spread of each part from the counts by class, and <M><mi>z</mi></M> from the file.
          </p>
        </Reproduce>

        <section aria-labelledby="data-h">
          <h2 id="data-h">The data</h2>
          <p data-attribution="source">
            Data: <a href={EUROLEAGUE.href}>{FILE.source}</a>.
          </p>
          <p data-attribution="affiliation">Not affiliated with EuroLeague.</p>
          <p data-attribution="aggregates">
            The feed has no open license, so this lesson publishes counts only: attempts, makes and points by season and zone
            class, never a shot, and no class with fewer than {r("k")} attempts. Removal requests:{" "}
            <a href={`mailto:${TAKEDOWN_CONTACT}`}>{TAKEDOWN_CONTACT}</a>.
          </p>
        </section>

        <section aria-labelledby="reading-h">
          <h2 id="reading-h">Further reading</h2>
          <ul>
            <li>
              <Cite id="mathworld-expectation" full />: the expected value of a random variable.
            </li>
            <li>
              <a href="/euroleague">Where EuroLeague shoots from</a>: the same feed, binned into hexagons on the court.
            </li>
          </ul>
        </section>
      </Band>
      <ExposeFigures file={FILE} />
    </main>
  );
}
