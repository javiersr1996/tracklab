import { Preview } from "../home/Preview";

// The head panel of an index (task 112): the section's sketch from the home's card, large. It is
// a picture, not data, so the whole panel is hidden from assistive technology.
export function SketchPanel({ href, label }: { href: string; label: string }) {
  return (
    <div className="head-panel head-panel-sketch" aria-hidden="true">
      <p className="head-panel-label">{label}</p>
      <Preview href={href} />
    </div>
  );
}
