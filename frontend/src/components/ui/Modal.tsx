'use client';

import { ReactNode, useEffect, useId } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence, useIsPresent } from 'framer-motion';
import { X } from 'lucide-react';
import { useScrollLock } from '@/hooks/useScrollLock';
import type { TourAnchorId } from '@/lib/tour/anchors';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  /** Names a dialog that shows no title of its own, for screen readers. */
  ariaLabel?: string;
  children: ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'full';
  /** Lets a tour light the whole dialog. */
  tourAnchor?: TourAnchorId;
}

const Modal = ({ isOpen, onClose, title, ariaLabel, children, size = 'md', tourAnchor }: ModalProps) => {
  const titleId = useId();
  useScrollLock(isOpen);

  // Close on escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  // Render through a portal to <body> so the fixed overlay isn't trapped inside
  // a transformed ancestor (e.g. a draggable/animated card) — a `position:fixed`
  // element is contained by any ancestor that has a CSS transform.
  if (typeof document === 'undefined') return null;

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <ModalLayer key="modal" onClose={onClose} title={title} titleId={titleId} ariaLabel={ariaLabel} size={size} tourAnchor={tourAnchor}>
          {children}
        </ModalLayer>
      )}
    </AnimatePresence>,
    document.body,
  );
};

const SIZES = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  full: 'max-w-full mx-4',
};

function ModalLayer({ onClose, title, titleId, ariaLabel, size, tourAnchor, children }: Omit<ModalProps, 'isOpen'> & {
  titleId: string;
  size: NonNullable<ModalProps['size']>;
}) {
  // A closed sheet is still fading out over the screen; presses in that time
  // belong to what is underneath, not to a sheet that is already gone.
  const present = useIsPresent();
  const reach = present ? '' : 'pointer-events-none';

  return (
    <>
      {/* Backdrop */}
      <motion.div
        className={`fixed inset-0 bg-black/40 backdrop-blur-sm z-40 ${reach}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      />

      {/* Center within Telegram's usable viewport. Very tall dialogs stay
          bounded and scroll internally instead of escaping the safe area. */}
      <div
        className={`fixed inset-0 z-50 flex items-center justify-center overflow-y-auto overscroll-contain pb-[calc(1rem+var(--content-safe-bottom))] pl-[calc(1rem+var(--content-safe-left))] pr-[calc(1rem+var(--content-safe-right))] pt-[calc(1rem+var(--content-safe-top))] ${reach}`}
        onClick={onClose}
      >
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-labelledby={title ? titleId : undefined}
          aria-label={title ? undefined : ariaLabel}
          data-tour={tourAnchor}
          className={`safe-modal-height relative flex w-full flex-col overflow-hidden rounded-[10px] border-[1.5px] border-outline bg-surface shadow-[var(--shadow-lifted)] ${SIZES[size]}`}
          initial={{ opacity: 0, scale: 0.97, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.97, y: 12 }}
          transition={{ type: 'spring', stiffness: 360, damping: 30 }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header — dark ink bar */}
          {title && (
            <div className="flex flex-shrink-0 items-center gap-2.5 bg-bar px-[18px] py-[15px] text-bar-fg">
              <h2 id={titleId} className="flex-1 font-display text-base font-bold">
                {title}
              </h2>
              <button
                onClick={onClose}
                aria-label="Close"
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[6px] text-bar-fg opacity-80 transition-[transform,opacity] hover:opacity-100 active:scale-[0.96]"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          )}

          {/* Content. A column, so a body marked min-h-0 shrinks to the sheet and
              scrolls only its list while the buttons under it stay in view. */}
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain p-5">{children}</div>
        </motion.div>
      </div>
    </>
  );
}

export default Modal;
