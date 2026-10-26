import { useSyncExternalStore } from "react";

// The reader's progress in /sql: the ids of the exercises solved, under one `localStorage` key.
// Every access to storage is in a try/catch, and the course works with storage throwing (a
// private window, a blocked origin): the verdict is still shown, and what was solved in this
// visit is kept in memory. Read through `useSyncExternalStore`, never `useEffect` + `setState`:
// the server renders nothing solved, and the client's real list replaces it before paint.
// The snapshot is the same array while storage holds the same text, as the hook requires.

export const STORAGE_KEY = "tracklab-sql-solved";

const EMPTY: readonly string[] = [];
let cachedText: string | null = null;
let cached: readonly string[] = EMPTY;
const listeners = new Set<() => void>();

function parse(text: string | null): readonly string[] {
  if (text === null) return EMPTY;
  try {
    const parsed: unknown = JSON.parse(text);
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : EMPTY;
  } catch {
    return EMPTY;
  }
}

export function solved(): readonly string[] {
  let text: string | null;
  try {
    text = localStorage.getItem(STORAGE_KEY);
  } catch {
    return cached;
  }
  if (text !== cachedText) {
    cachedText = text;
    cached = parse(text);
  }
  return cached;
}

export function markSolved(id: string): void {
  const current = solved();
  if (current.includes(id)) return;
  cached = [...current, id];
  cachedText = JSON.stringify(cached);
  try {
    localStorage.setItem(STORAGE_KEY, cachedText);
  } catch {
    // Kept in memory for this visit.
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab of this site solving an exercise.
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === STORAGE_KEY) listener();
  };
  try {
    window.addEventListener("storage", onStorage);
  } catch {
    // No window: nothing to listen to.
  }
  return () => {
    listeners.delete(listener);
    try {
      window.removeEventListener("storage", onStorage);
    } catch {
      // As above.
    }
  };
}

const getServerSnapshot = () => EMPTY;

export const useSolved = (): readonly string[] => useSyncExternalStore(subscribe, solved, getServerSnapshot);
