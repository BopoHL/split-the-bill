'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { Smartphone, X } from 'lucide-react';
import Button from '@/components/ui/Button';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { useHomeScreenShortcut } from '@/hooks/useHomeScreenShortcut';

export default function HomeScreenBanner() {
  const { t } = useTranslation();
  const {
    showBanner,
    isPending,
    add,
    dismiss,
  } = useHomeScreenShortcut();

  return (
    <>
      <AnimatePresence>
        {showBanner && (
          <motion.div
            initial={{ opacity: 0, y: -8, filter: 'blur(4px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -8, filter: 'blur(4px)' }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="relative mb-5 grid grid-cols-[2.5rem_minmax(0,1fr)] items-start gap-x-3 gap-y-3 rounded-[10px] border-[1.5px] border-outline bg-surface px-3.5 py-3 shadow-[var(--shadow-lifted)] sm:grid-cols-[2.5rem_minmax(0,1fr)_auto_auto] sm:items-center"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[8px] border-[1.5px] border-outline bg-accent/15 text-accent">
              <Smartphone className="h-5 w-5" />
            </span>

            <div className="min-w-0 pr-8 sm:pr-0">
              <p className="font-display text-[14px] font-bold leading-tight text-foreground">
                {t('homeScreen.bannerTitle')}
              </p>
              <p className="mt-0.5 text-pretty text-[12px] font-medium leading-snug text-muted">
                {t('homeScreen.bannerText')}
              </p>
            </div>

            <Button
              variant="primary"
              size="sm"
              onClick={add}
              isLoading={isPending}
              className="col-start-2 w-full sm:col-start-3 sm:row-start-1 sm:w-auto"
            >
              {isPending ? t('homeScreen.checking') : t('homeScreen.add')}
            </Button>

            <button
              type="button"
              onClick={dismiss}
              aria-label={t('common.close')}
              className="absolute right-1.5 top-1.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-foreground sm:static sm:col-start-4 sm:row-start-1 sm:-mr-1"
            >
              <X className="h-4 w-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
