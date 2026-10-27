import { display } from "../../lib/learn/display";
import { fact, type SqlSlug } from "../../lib/sql/course";

// A number or a name a lesson of /sql prints: the value `facts.sql` computed for it, carried as
// `data-fact` so a test can compare the page with course.json. A fact the lesson does not have
// fails the build, so nothing is typed.
export function Fact({ lesson, name }: { lesson: SqlSlug; name: string }) {
  return <span data-fact={name}>{display(fact(lesson, name), name)}</span>;
}

// The `f("name")` a lesson's prose uses.
export const factOf = (lesson: SqlSlug) =>
  function f(name: string) {
    return <Fact lesson={lesson} name={name} />;
  };
