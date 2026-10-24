// The /learn series in the order it is read. `status` is what the index shows: a published lesson
// links to its page, one in preparation is listed without a link. A lesson that comes after the
// Analytics Cup fence (lib/learn/fence.json) is not listed at all, so it has no entry here.
export type Level = "Foundations" | "Intermediate" | "Advanced";

export interface Lesson {
  n: number;
  slug: string;
  title: string;
  level: Level;
  status: "published" | "in-preparation";
  about: string;
}

export const LESSONS: readonly Lesson[] = [
  {
    n: 1,
    slug: "gravity",
    title: "Does the ball obey gravity?",
    level: "Foundations",
    status: "published",
    about: "Least squares on a flight of the ball, its residuals, and what a per-match figure can and cannot say.",
  },
  {
    n: 2,
    slug: "speed",
    title: "Where does the provider's speed come from?",
    level: "Foundations",
    status: "published",
    about: "Finite differences, noise and a moving average, and a speed field that behaves like its own positions, differentiated.",
  },
  {
    n: 3,
    slug: "coordinates",
    title: "Can a court and a pitch share one table?",
    level: "Foundations",
    status: "published",
    about: "Coordinates, affine transforms, sampling rate and linear interpolation.",
  },
  {
    n: 4,
    slug: "rebound",
    title: "Who gets to the rebound first?",
    level: "Intermediate",
    status: "published",
    about: "A kinematic time to arrive and a logistic model of who wins the ball.",
  },
  {
    n: 5,
    slug: "cadence",
    title: "How many steps per second?",
    level: "Advanced",
    status: "published",
    about: "Periodicity in body pose and how a predicted error propagates into it.",
  },
  {
    n: 6,
    slug: "clock",
    title: "Does the game clock keep the video's time?",
    level: "Foundations",
    status: "published",
    about: "A least-squares line through two clocks, its residuals, and what a wrong second would do to a speed and to g.",
  },
  {
    n: 7,
    slug: "pass",
    title: "How fast does a pass travel?",
    level: "Intermediate",
    status: "published",
    about: "Chord and path of the ball, and what the provider's distance of a pass measures instead.",
  },
  {
    n: 8,
    slug: "entry",
    title: "At what angle does the ball reach the rim?",
    level: "Intermediate",
    status: "published",
    about: "Projectile geometry against the file's heights, a method tried on a perfect flight, and what g and a height scale move.",
  },
];

export const lessonHref = (l: Lesson) => `/learn/${l.slug}`;
