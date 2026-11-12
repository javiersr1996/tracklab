import { THUMB, thumbOf } from "../../lib/learn/thumbs";

// A lesson's drawing on /learn (task 182), rendered on the server from `lib/learn/thumbs.ts`. It is
// decoration for a screen reader: the link beside it names the lesson, and the lesson prints every
// fact the drawing shows.
export function Thumb({ slug }: { slug: string }) {
  const marks = thumbOf(slug);
  if (!marks) return null;
  return (
    <svg
      className="lesson-thumb"
      data-thumb={slug}
      viewBox={`0 0 ${THUMB.w} ${THUMB.h}`}
      aria-hidden="true"
      focusable="false"
    >
      {marks.map((m, i) => {
        const tone = `thumb-${m.tone}`;
        if (m.kind === "dots") {
          return (
            <g key={i} className={tone}>
              {m.at.map(([x, y], k) => (
                <circle key={k} cx={x} cy={y} r={m.r} />
              ))}
            </g>
          );
        }
        if (m.kind === "rect") return <rect key={i} className={tone} x={m.x} y={m.y} width={m.w} height={m.h} />;
        if (m.kind === "fill") return <path key={i} className={tone} d={m.d} />;
        return <path key={i} className={`${tone} thumb-stroke${m.dashed ? " thumb-dashed" : ""}`} d={m.d} />;
      })}
    </svg>
  );
}
