'use client';

import { motion, useReducedMotion } from 'framer-motion';

const RECEIPT_LINES = ['78%', '54%', '66%', '40%', '72%', '48%'];

/** A receipt with a scan line running over it, while one is being read. */
export default function ScanAnimation() {
  const reduceMotion = useReducedMotion();
  return (
    <div
      aria-hidden="true"
      className="relative mx-auto mb-5 h-[124px] w-[100px] overflow-hidden rounded-[6px] border-[1.5px] border-outline bg-background px-3 py-3.5 shadow-[var(--shadow-hard-sm)]"
    >
      {RECEIPT_LINES.map((width, index) => (
        <span key={index} style={{ width }} className="mb-2 block h-[5px] rounded-full bg-border" />
      ))}
      {!reduceMotion && (
        <motion.span
          className="absolute inset-x-0 h-[2px] bg-accent shadow-[0_0_10px_var(--accent)]"
          initial={{ top: '6%' }}
          animate={{ top: ['6%', '92%', '6%'] }}
          transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
    </div>
  );
}
