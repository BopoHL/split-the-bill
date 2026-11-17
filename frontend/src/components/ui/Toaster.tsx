'use client';

import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, Check, Info, X, type LucideIcon } from 'lucide-react';
import { useStore, type ToastVariant } from '@/lib/store/useStore';
import { useTranslation } from '@/lib/i18n/useTranslation';

const BADGES: Record<ToastVariant, { icon: LucideIcon; strokeWidth?: number; className: string }> = {
  error: { icon: AlertTriangle, className: 'border-danger bg-danger text-danger-fg' },
  success: { icon: Check, strokeWidth: 2.5, className: 'border-success bg-success text-success-fg' },
  info: { icon: Info, strokeWidth: 2.5, className: 'border-outline bg-foreground text-background' },
};

/**
 * Renders the current toast (styled, Bold) and auto-dismisses it. Mounted once
 * at the app root; messages are pushed via `showToast()`.
 */
export default function Toaster() {
  const { t } = useTranslation();
  const toast = useStore((s) => s.toast);
  const dismiss = useStore((s) => s.dismissToast);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(dismiss, 3800);
    return () => clearTimeout(id);
  }, [toast, dismiss]);

  const badge = toast ? BADGES[toast.variant] : null;

  return (
    <AnimatePresence>
      {badge && toast && (
        <motion.div
          key={toast.id}
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ type: 'spring', stiffness: 420, damping: 30 }}
          // Below Telegram's own chrome: in fullscreen the close/menu buttons
          // sit over the top of the page and swallowed the toast.
          style={{ top: 'calc(1rem + var(--content-safe-top))' }}
          className="fixed inset-x-0 z-[90] flex justify-center pl-[calc(1rem+var(--content-safe-left))] pr-[calc(1rem+var(--content-safe-right))]"
        >
          <div className="flex w-full max-w-md items-start gap-3 rounded-lg border-[1.5px] border-outline bg-surface px-4 py-3 shadow-[var(--shadow-lifted)]">
            <span
              className={`mt-px flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md border-[1.5px] ${badge.className}`}
            >
              <badge.icon className="h-4 w-4" strokeWidth={badge.strokeWidth} />
            </span>
            <span className="min-w-0 flex-1 pt-0.5 text-sm font-medium leading-snug text-foreground">
              {toast.message}
            </span>
            <button
              onClick={dismiss}
              aria-label={t('common.cancel')}
              className="mt-px flex-shrink-0 text-muted-2 transition-colors hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
