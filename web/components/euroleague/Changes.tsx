import { type Change, seasonLabel, signedPp, type TeamChanges, wholePct, type Zone } from "../../lib/euroleague/atlas";
import { Band } from "../site/Band";

const PARTS: { zone: Zone; name: string }[] = [
  { zone: "rim", name: "near the rim" },
  { zone: "mid", name: "mid-range" },
  { zone: "three", name: "threes" },
];

const oneDecimal = (share: number) => `${(share * 100).toFixed(1)}%`;

// The change in a team's share of threes from the first season to the second, when it played both.
function threeDelta(t: TeamChanges, seasons: readonly string[]): number | null {
  const [a, b] = seasons.map((s) => t.changes.find((c) => c.season === s));
  return a && b ? b.three.share - a.three.share : null;
}

function Bar({ change, season }: { change: Change; season: string }) {
  const words = PARTS.map((p) => `${p.name} ${oneDecimal(change[p.zone].share)}`).join(", ");
  return (
    <div className="el-bar-row">
      <span className="el-bar-season">{seasonLabel(season).slice(2)}</span>
      <div className="el-bar" role="img" aria-label={`${seasonLabel(season)}: ${words}`} data-bar={season}>
        {PARTS.map((p) => {
          const share = change[p.zone].share;
          return (
            <span key={p.zone} className="el-seg" data-zone={p.zone} style={{ flexGrow: share }}>
              {share >= 0.1 ? wholePct(share) : ""}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// "What has changed" (task 116): for each team, how its field goals split between near the rim,
// mid-range and threes in each season, and its share of fast breaks, from the `changes` of its
// file. The teams are sorted by the change in their share of threes; one that played a single
// season goes last. The team chosen in the atlas comes first, lit.
export function Changes({
  changes,
  seasons,
  selected,
}: {
  changes: TeamChanges[];
  seasons: readonly string[];
  selected: string;
}) {
  const sorted = [...changes].sort((a, b) => {
    if (a.code === selected || b.code === selected) return a.code === selected ? -1 : 1;
    const [da, db] = [threeDelta(a, seasons), threeDelta(b, seasons)];
    if (da === null || db === null) return da === db ? a.name.localeCompare(b.name) : da === null ? 1 : -1;
    return db - da || a.name.localeCompare(b.name);
  });
  const [first, second] = seasons.map(seasonLabel);
  return (
    <Band className="el-changes-band">
      <section aria-labelledby="el-changes-title">
        <h2 id="el-changes-title">What has changed</h2>
        <p>
          Each bar splits a team&apos;s field goals in one season between twos near the rim (white), mid-range
          twos (grey) and threes (cyan); the top bar is {first}, the bottom {second}. Teams are sorted by how much
          their share of threes moved between the two, with the team chosen above first.
        </p>
        <ol className="el-changes">
          {sorted.map((t) => {
            const delta = threeDelta(t, seasons);
            const played = seasons.flatMap((s) => t.changes.filter((c) => c.season === s));
            return (
              <li
                key={t.code}
                className="el-change"
                data-change-team={t.code}
                data-selected={selected === t.code ? "true" : undefined}
                aria-current={selected === t.code ? "true" : undefined}
              >
                <h3 className="el-change-name">{t.name}</h3>
                <p className="el-change-delta">
                  {delta === null ? "One season" : `Threes ${signedPp(delta)}`}
                </p>
                {seasons.map((s) => {
                  const c = t.changes.find((x) => x.season === s);
                  return c ? (
                    <Bar key={s} change={c} season={s} />
                  ) : (
                    <p key={s} className="el-bar-missing">
                      Not in the {seasonLabel(s)} EuroLeague
                    </p>
                  );
                })}
                <p className="el-change-fast">
                  Fast-break shots {played.map((c) => oneDecimal(c.fastbreak.share)).join(" → ")}
                </p>
              </li>
            );
          })}
        </ol>
      </section>
    </Band>
  );
}
