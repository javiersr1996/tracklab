// The Gantt and the history charts draw their text at 12 user units; the svg is shown at this
// factor so it reads at 16 px, the floor (`--step-0`) every other figure of the site keeps (P19,
// task 152). The lineage graph's own SCALE is 2 for the same reason (8 units).
export const GANTT_SCALE = 16 / 12;
