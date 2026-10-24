// How a lesson prints a value of a file: a count of five digits or more takes thousands
// separators, and the prefix of an id the reader does not need (`bb:114086`, `shot-114086-1-28`)
// is left off. A figure whose name ends in `id` is an id, never a count. The tests compare the
// page with `display(source, name)`, so the figure is still the file's.
export function display(value: string, name: string): string {
  if (!/id$/.test(name) && /^\d{5,}$/.test(value)) return Number(value).toLocaleString("en-US");
  return value.replace(/^(?:bb|fb):/, "").replace(/^shot-/, "");
}
