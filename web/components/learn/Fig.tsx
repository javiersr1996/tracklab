// A figure the lesson shows: its path in the artifact it was read from, and the text. The e2e
// compares each one with the file, so a number typed here would fail.
import { display } from "../../lib/learn/display";

export function Fig({ name, children }: { name: string; children: string | number }) {
  return <span data-fig={name}>{display(String(children), name)}</span>;
}
