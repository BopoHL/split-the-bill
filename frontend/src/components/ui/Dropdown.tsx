'use client';

import { useRef, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { LucideIcon } from 'lucide-react';
import { useDismiss } from '@/hooks/useDismiss';

/**
 * A menu that drops from a button in the header: it closes on a press outside
 * it or on Escape, and its rows are pills inset from its edges, so a hover
 * never runs into the border or the dividers around it.
 */
export default function Dropdown({ open, onClose, trigger, label, className = '', children }: {
  open: boolean;
  onClose: () => void;
  trigger: ReactNode;
  label: string;
  className?: string;
  children: ReactNode;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  useDismiss(rootRef, open, onClose);

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      {trigger}
      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            aria-label={label}
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 z-30 mt-2 min-w-[200px] overflow-hidden rounded-xl border-[1.5px] border-outline bg-surface py-1.5 text-foreground shadow-[var(--shadow-lifted)]"
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const ROW = 'mx-1.5 flex w-[calc(100%-0.75rem)] items-center gap-2.5 rounded-lg px-2 py-2 text-left text-sm transition-colors hover:bg-surface-2';

/** A row that does something. */
export function DropdownAction({ icon: Icon, label, onClick, disabled }: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button onClick={onClick} disabled={disabled} className={ROW}>
      <Icon className="h-4 w-4 shrink-0 text-muted" />
      {label}
    </button>
  );
}

/** A row that opens something with more in it, showing what is chosen there. */
export function DropdownRow({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} className={`${ROW} mb-1`}>
      {children}
    </button>
  );
}

export function DropdownLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-3.5 pb-1 pt-1.5 font-display text-[10px] font-bold uppercase tracking-[0.14em] text-muted">
      {children}
    </div>
  );
}

export function DropdownDivider() {
  return <div className="mx-3.5 my-1.5 h-px bg-border" />;
}
