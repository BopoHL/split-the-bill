import { useEffect, useState } from 'react';

/** The time now, ticking every second until `until` — for a countdown to that
 *  moment. With nothing ahead it stands still. */
export function useNow(until: number | null): Date {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    if (until === null) return;
    const tick = () => {
      const current = new Date();
      setNow(current);
      if (current.getTime() >= until) clearInterval(timer);
    };
    // Straight away too: the clock may have stood still since long before.
    const first = setTimeout(tick, 0);
    const timer = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [until]);

  return now;
}
