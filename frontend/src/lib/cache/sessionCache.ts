/**
 * Answers the app already had this session, kept so that coming back to one —
 * another period, another filter, the screen opened again — shows it at once
 * while a fresh answer is asked for. Bounded: the oldest go first.
 */
export interface SessionCache<T> {
  get: (key: string) => T | undefined;
  set: (key: string, value: T) => void;
  /** Every answer kept, oldest first. */
  entries: () => [string, T][];
  /** Change every kept answer — after something they all show has gone. */
  update: (change: (value: T, key: string) => T) => void;
  clear: () => void;
}

const caches = new Set<SessionCache<unknown>>();

export function createSessionCache<T>(limit = 24): SessionCache<T> {
  const kept = new Map<string, T>();
  const cache: SessionCache<T> = {
    get: (key) => kept.get(key),
    set: (key, value) => {
      kept.delete(key);
      kept.set(key, value);
      if (kept.size > limit) kept.delete(kept.keys().next().value as string);
    },
    entries: () => [...kept.entries()],
    update: (change) => {
      for (const [key, value] of kept) kept.set(key, change(value, key));
    },
    clear: () => kept.clear(),
  };
  caches.add(cache as SessionCache<unknown>);
  return cache;
}

/** Forget everything kept — for a fresh start between tests. */
export function clearSessionCaches(): void {
  caches.forEach((cache) => cache.clear());
}
