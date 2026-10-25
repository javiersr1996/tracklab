// The /learn series in the order it is read. `status` is what the index shows: a published lesson
// links to its page, one in preparation is listed without a link. A lesson that comes after the
// Analytics Cup fence (lib/learn/fence.json) is not listed at all, so it has no entry here.
export type Level = "Foundations" | "Intermediate" | "Advanced";

export type Sport = "Basketball" | "Football" | "Basketball and football";

export interface Lesson {
  n: number;
  slug: string;
  title: string;
  level: Level;
  sport: Sport;
  status: "published" | "in-preparation";
  about: string;
}

export const LESSONS: readonly Lesson[] = [
  {
    n: 1,
    slug: "gravity",
    title: "Does the ball obey gravity?",
    level: "Foundations",
    sport: "Basketball",
    status: "published",
    about: "Least squares on a flight of the ball, its residuals, and what a per-match figure can and cannot say.",
  },
  {
    n: 2,
    slug: "speed",
    title: "Where does the provider's speed come from?",
    level: "Foundations",
    sport: "Basketball",
    status: "published",
    about: "Finite differences, noise and a moving average, and a speed field that behaves like its own positions, differentiated.",
  },
  {
    n: 3,
    slug: "coordinates",
    title: "Can a court and a pitch share one table?",
    level: "Foundations",
    sport: "Basketball and football",
    status: "published",
    about: "Coordinates, affine transforms, sampling rate and linear interpolation.",
  },
  {
    n: 4,
    slug: "rebound",
    title: "Who gets to the rebound first?",
    level: "Intermediate",
    sport: "Basketball",
    status: "published",
    about: "A kinematic time to arrive and a logistic model of who wins the ball.",
  },
  {
    n: 5,
    slug: "cadence",
    title: "How many steps per second?",
    level: "Advanced",
    sport: "Football",
    status: "published",
    about: "Periodicity in body pose and how a predicted error propagates into it.",
  },
  {
    n: 6,
    slug: "clock",
    title: "Does the game clock keep the video's time?",
    level: "Foundations",
    sport: "Basketball",
    status: "published",
    about: "A least-squares line through two clocks, its residuals, and what a wrong second would do to a speed and to g.",
  },
  {
    n: 7,
    slug: "pass",
    title: "How fast does a pass travel?",
    level: "Intermediate",
    sport: "Basketball",
    status: "published",
    about: "Chord and path of the ball, and what the provider's distance of a pass measures instead.",
  },
  {
    n: 8,
    slug: "entry",
    title: "At what angle does the ball reach the rim?",
    level: "Intermediate",
    sport: "Basketball",
    status: "published",
    about: "Projectile geometry against the file's heights, a method tried on a perfect flight, and what g and a height scale move.",
  },
  {
    n: 9,
    slug: "dribble",
    title: "How many bounces per second?",
    level: "Intermediate",
    sport: "Basketball",
    status: "published",
    about: "Events as points in time, their intervals, matching them to the ball's height, and the height's own rhythm.",
  },
  {
    n: 10,
    slug: "possession",
    title: "How often does possession change hands?",
    level: "Intermediate",
    sport: "Basketball and football",
    status: "published",
    about: "Three units of possession, durations as a distribution, and a survival curve against an exponential with the same median.",
  },
  {
    n: 11,
    slug: "facing",
    title: "Which way is a player facing?",
    level: "Advanced",
    sport: "Football",
    status: "published",
    about: "A direction from two shoulders and a nose, set against the direction of travel, and a mean and a variance that know the circle closes.",
  },
];

export const lessonHref = (l: Lesson) => `/learn/${l.slug}`;

export const LEVELS: readonly Level[] = ["Foundations", "Intermediate", "Advanced"];
