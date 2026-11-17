import { motion, AnimatePresence } from 'framer-motion';
import { Plus } from 'lucide-react';
import type { TourAnchorId } from '@/lib/tour/anchors';

interface FloatingCreateButtonProps {
  onClick: () => void;
  ariaLabel: string;
  show?: boolean;
  tourAnchor?: TourAnchorId;
}

export default function FloatingCreateButton({
  onClick,
  ariaLabel,
  show = true,
  tourAnchor,
}: FloatingCreateButtonProps) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          className="pointer-events-none fixed inset-x-0 bottom-[calc(1.8125rem+var(--content-safe-bottom))] z-50 pl-[var(--content-safe-left)] pr-[var(--content-safe-right)]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
        >
          <div className="mx-auto flex w-full max-w-2xl justify-end px-7">
            <motion.button
              type="button"
              onClick={onClick}
              aria-label={ariaLabel}
              data-tour={tourAnchor}
              className="btn-hard pointer-events-auto flex h-[66px] w-[66px] shrink-0 items-center justify-center rounded-[13px] border-[1.5px] border-outline bg-accent text-accent-fg"
              whileTap={{ x: 4, y: 5 }}
              transition={{ x: { duration: 0 }, y: { duration: 0 } }}
            >
              <Plus className="h-[30px] w-[30px]" strokeWidth={2.25} />
            </motion.button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
