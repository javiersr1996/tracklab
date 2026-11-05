// Lesson 12's arithmetic on counts by zone class (task 117), written again here, apart from the
// pipeline's: vitest sets it against every row of expected-points.json and against figures worked
// out by hand.
import { CLASSES, type Tally, type ZoneClass, type Zones } from "./expected-data";

// A class's points per attempt: its value times the share made, which is its points over its
// attempts.
export const perShot = (t: Tally): number => t.pts / t.n;

export const perShotByClass = (z: Zones): Record<ZoneClass, number> =>
  Object.fromEntries(CLASSES.map((c) => [c, perShot(z[c])])) as Record<ZoneClass, number>;

export const attempts = (z: Zones): number => CLASSES.reduce((s, c) => s + z[c].n, 0);

// The league's points per shot over the three classes: each class's points per shot weighted by
// its attempts, which is all its points over all its attempts.
export const weightedMean = (z: Zones): number => CLASSES.reduce((s, c) => s + z[c].n * perShot(z[c]), 0) / attempts(z);

// The plain mean of the three classes, as if each were tried as often: what the weights change.
export const plainMean = (z: Zones): number => CLASSES.reduce((s, c) => s + perShot(z[c]), 0) / CLASSES.length;

// A team against the league: its points per shot, its expected points per shot (each attempt at
// the league's points per shot for its class), and the two parts of the difference with the
// league's mean, mix = xpps - mean and making = pps - xpps.
export function split(team: Zones, league: Zones) {
  const e = perShotByClass(league);
  const n = attempts(team);
  const pps = CLASSES.reduce((s, c) => s + team[c].pts, 0) / n;
  const xpps = CLASSES.reduce((s, c) => s + team[c].n * e[c], 0) / n;
  const mean = weightedMean(league);
  return { pps, xpps, mix: xpps - mean, making: pps - xpps };
}

// What a make in each class scores: a three 3, a two 2.
const VALUE: Record<ZoneClass, number> = { rim: 2, mid: 2, three: 3 };

// The intervals of mix and making if the team's attempts were independent draws, each from its own
// mix of classes and made at its own rate there (task 117b). Both parts are means over the attempts,
// of e_z − ē for mix and of the attempt's points − e_z for making, so each standard error is the
// spread of those over √n, and the interval is the part ∓ z of them. Unrounded.
export function intervals(team: Zones, league: Zones, z: number) {
  const e = perShotByClass(league);
  const mean = weightedMean(league);
  const n = attempts(team);
  const { mix, making } = split(team, league);
  let mixSq = 0;
  let makingSq = 0;
  for (const c of CLASSES) {
    mixSq += team[c].n * (e[c] - mean) ** 2;
    makingSq += team[c].made * (VALUE[c] - e[c]) ** 2 + (team[c].n - team[c].made) * e[c] ** 2;
  }
  const seMix = Math.sqrt((mixSq / n - mix ** 2) / n);
  const seMaking = Math.sqrt((makingSq / n - making ** 2) / n);
  return { mix: [mix - z * seMix, mix + z * seMix], making: [making - z * seMaking, making + z * seMaking] };
}

// A team's share of its attempts in each class.
export const shares = (z: Zones): Record<ZoneClass, number> =>
  Object.fromEntries(CLASSES.map((c) => [c, z[c].n / attempts(z)])) as Record<ZoneClass, number>;

