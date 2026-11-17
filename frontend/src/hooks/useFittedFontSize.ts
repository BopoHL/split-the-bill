import { useEffect, useRef, useState } from 'react';

/**
 * The size, in half pixels, at which a line `widthAtMax` wide at `max` fits
 * `room`, but no smaller than `min`; `clipped` once even that is too wide.
 * A line of one font grows in step with its size, which this relies on.
 */
export function fitFontSize(widthAtMax: number, room: number, max: number, min: number) {
  const size = Math.max(min, Math.min(max, Math.floor(((max * room) / widthAtMax) * 2) / 2));
  return { size, clipped: (widthAtMax * size) / max > room + 0.5 };
}

/**
 * Shrinks a one-line text to fit its box as the box or the text changes. The
 * text sits inline in the box, so its own width is its full width even while
 * the box cuts it off.
 */
export function useFittedFontSize<Box extends HTMLElement, Text extends HTMLElement>(text: string, max: number, min: number) {
  const boxRef = useRef<Box>(null);
  const textRef = useRef<Text>(null);
  const [fit, setFit] = useState({ size: max, clipped: false });

  useEffect(() => {
    const box = boxRef.current;
    const line = textRef.current;
    if (!box || !line || typeof ResizeObserver === 'undefined') return;
    const measure = () => {
      const current = parseFloat(getComputedStyle(line).fontSize);
      const width = line.getBoundingClientRect().width;
      if (!current || !width || !box.clientWidth) return;
      setFit(fitFontSize((width * max) / current, box.clientWidth, max, min));
    };
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, [text, max, min]);

  return { boxRef, textRef, ...fit };
}
