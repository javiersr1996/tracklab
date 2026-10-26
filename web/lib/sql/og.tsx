import { card } from "../learn/og";
import { type SqlSlug, sqlLessonMeta } from "./course";

// The cards the links to /sql and its lessons unfurl into: the same card as /learn's, with the
// lesson's question and "Lesson n · concept". No figure of any kind.
export { OG_SIZE, OG_TYPE } from "../learn/og";

export const sqlImage = (slug: SqlSlug) => {
  const l = sqlLessonMeta(slug);
  return card(`SQL lesson ${l.n} · ${l.concept}`, l.title);
};

export const sqlIndexImage = () => card("Learn SQL", "Learn SQL on the warehouse");
