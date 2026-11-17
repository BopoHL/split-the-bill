'use client';

import { useId, type CSSProperties } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Pointer } from 'lucide-react';
import type { Box } from '@/lib/tour/visibility';

const PAD = 6;
const RADIUS = 12;
const DIM = 'rgba(10, 8, 6, 0.64)';
const HAND_SIZE = 38;

/**
 * - `pass`: presses in the hole reach the element — it is the real thing;
 * - `block`: the element is only to be looked at;
 * - `catch`: the press is the tour's, the element is left alone.
 */
export type HoleMode = 'pass' | 'block' | 'catch';

interface SpotlightProps {
  box: Box | null;
  mode: HoleMode;
  catchLabel?: string;
  onCatch?: () => void;
}

const px = (box: Box): CSSProperties => ({ top: box.top, left: box.left, width: box.width, height: box.height });

/** Everything dimmed and out of reach except one element. With nothing to
 *  light yet, the whole screen waits under the dim. */
export default function Spotlight({ box, mode, catchLabel, onCatch }: SpotlightProps) {
  const maskId = useId();
  const reduceMotion = useReducedMotion();
  const hole = box && {
    top: box.top - PAD,
    left: box.left - PAD,
    width: box.width + PAD * 2,
    height: box.height + PAD * 2,
  };

  // Walled off right up to the element itself: the padding around it is only
  // for looks, and a press landing there must not reach whatever lies under it.
  const blockers: CSSProperties[] = box
    ? [
        { top: 0, left: 0, right: 0, height: Math.max(0, box.top) },
        { top: box.top + box.height, left: 0, right: 0, bottom: 0 },
        { top: box.top, left: 0, width: Math.max(0, box.left), height: box.height },
        { top: box.top, left: box.left + box.width, right: 0, height: box.height },
      ]
    : [{ inset: 0 }];

  const pointsAtIt = hole && mode !== 'block';

  return (
    <>
      <svg aria-hidden="true" className="pointer-events-none fixed inset-0 h-full w-full">
        <defs>
          <mask id={maskId}>
            <rect width="100%" height="100%" fill="white" />
            {hole && <rect x={hole.left} y={hole.top} width={hole.width} height={hole.height} rx={RADIUS} fill="black" />}
          </mask>
        </defs>
        <rect width="100%" height="100%" fill={DIM} mask={`url(#${maskId})`} />
      </svg>

      {blockers.map((style, index) => (
        <div key={index} style={style} className="pointer-events-auto fixed touch-none" />
      ))}

      {hole && mode === 'block' && <div style={px(hole)} className="pointer-events-auto fixed touch-none" />}
      {hole && mode === 'catch' && (
        <button
          type="button"
          aria-label={catchLabel}
          onClick={onCatch}
          style={px(hole)}
          className="pointer-events-auto fixed rounded-[12px]"
        />
      )}

      {hole && (
        <div
          aria-hidden="true"
          style={px(hole)}
          className={`pointer-events-none fixed rounded-[12px] border-2 border-accent ${pointsAtIt ? 'tour-glow' : ''}`}
        />
      )}

      {pointsAtIt && (
        <motion.span
          aria-hidden="true"
          style={{
            // The fingertip of the icon sits at about a third across its top.
            top: hole.top + hole.height / 2 + 4,
            left: hole.left + hole.width / 2 - HAND_SIZE / 3,
          }}
          className="pointer-events-none fixed text-foreground drop-shadow-[0_2px_0_var(--surface)]"
          animate={reduceMotion ? undefined : { y: [10, 0, 10], scale: [1, 0.92, 1] }}
          transition={{ duration: 1.3, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Pointer className="fill-surface" style={{ width: HAND_SIZE, height: HAND_SIZE }} strokeWidth={1.75} />
        </motion.span>
      )}
    </>
  );
}
