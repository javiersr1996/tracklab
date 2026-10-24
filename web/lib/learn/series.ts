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
    about: "Finite differences, noise and a moving average, and a speed field derived from its own positions.",
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
];

export const lessonHref = (l: Lesson) => `/learn/${l.slug}`;
