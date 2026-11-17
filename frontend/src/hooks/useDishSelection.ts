import { useState } from 'react';

/** The dishes of a receipt picked to be handed out together, by position key. */
export interface DishSelection {
  active: boolean;
  keys: ReadonlySet<string>;
  start: () => void;
  stop: () => void;
  /** Picks every given dish, or drops them all when every one is picked already. */
  toggle: (keys: string[]) => void;
  add: (keys: string[]) => void;
  clear: () => void;
}

export function useDishSelection(): DishSelection {
  const [active, setActive] = useState(false);
  const [keys, setKeys] = useState<ReadonlySet<string>>(new Set());
  return {
    active,
    keys,
    start: () => setActive(true),
    stop: () => {
      setActive(false);
      setKeys(new Set());
    },
    toggle: (group) => setKeys((previous) => {
      const next = new Set(previous);
      const picked = group.every((key) => next.has(key));
      for (const key of group) {
        if (picked) next.delete(key);
        else next.add(key);
      }
      return next;
    }),
    add: (group) => setKeys((previous) => new Set([...previous, ...group])),
    clear: () => setKeys(new Set()),
  };
}
