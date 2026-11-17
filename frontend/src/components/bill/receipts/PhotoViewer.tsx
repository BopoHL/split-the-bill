'use client';

import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useScrollLock } from '@/hooks/useScrollLock';
import { showBackButton } from '@/lib/telegram/init';

interface PhotoViewerProps {
  src: string | null;
  onClose: () => void;
}

/**
 * Full-screen look at a receipt.
 *
 * Opening it in a new tab handed the screen to the browser and came back with a
 * zoomed webview — the exact bug the viewport work went after. Keeping it inside
 * the app avoids the round trip entirely.
 */
export default function PhotoViewer({ src, onClose }: PhotoViewerProps) {
  useScrollLock(!!src);

  useEffect(() => {
    if (!src) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);

    // While the photo is up, Telegram's own back button has to close it —
    // otherwise the only obvious way out of a full-screen image leaves the bill.
    const releaseBack = showBackButton(onClose);

    return () => {
      document.removeEventListener('keydown', onKey);
      releaseBack();
    };
  }, [src, onClose]);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <AnimatePresence>
      {src && (
        <motion.div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/90"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="absolute flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-white"
            style={{
              top: 'calc(1rem + var(--content-safe-top))',
              right: 'calc(1rem + var(--content-safe-right))',
            }}
          >
            <X className="h-6 w-6" />
          </button>

          <motion.img
            src={src}
            alt=""
            initial={{ scale: 0.96 }}
            animate={{ scale: 1 }}
            exit={{ scale: 0.96 }}
            onClick={(e) => e.stopPropagation()}
            className="max-h-full max-w-full rounded-[8px] object-contain"
            style={{
              // Room to tap around the image: it fills the screen otherwise and
              // there is nowhere to aim for «close».
              maxHeight: 'calc(100dvh - 8rem - var(--content-safe-top) - var(--content-safe-bottom))',
              maxWidth: 'calc(100vw - 2.5rem - var(--content-safe-left) - var(--content-safe-right))',
            }}
          />
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
