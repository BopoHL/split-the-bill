'use client';

import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { PartyPopper } from 'lucide-react';
import Button from '@/components/ui/Button';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { EASE_OUT } from '@/lib/motion';
import { useTour } from '@/lib/tour/useTour';
import { useTourExit } from './useTourExit';

/** The last words, back on the home screen with the demo bill already gone. */
export default function TourFinale() {
  const { t } = useTranslation();
  const { complete } = useTourExit();
  const completed = useRef(false);

  useEffect(() => {
    if (completed.current) return;
    completed.current = true;
    complete();
  }, [complete]);

  return (
    <div className="pointer-events-auto fixed inset-0 flex touch-none items-center justify-center bg-black/60 pl-[calc(1rem+var(--content-safe-left))] pr-[calc(1rem+var(--content-safe-right))]">
      <motion.div
        initial={{ opacity: 0, scale: 0.94 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.28, ease: EASE_OUT }}
        className="w-full max-w-sm rounded-[12px] border-[1.5px] border-outline bg-surface p-6 text-center text-foreground shadow-[var(--shadow-hard)]"
      >
        <span className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-[12px] border-[1.5px] border-outline bg-accent text-accent-fg shadow-[var(--shadow-hard-sm)]">
          <PartyPopper className="h-7 w-7" />
        </span>
        <h2 className="text-balance font-display text-[20px] font-bold">{t('tour.finale.title')}</h2>
        <p className="mx-auto mt-2 max-w-[280px] text-pretty text-[14px] font-medium leading-relaxed text-muted">
          {t('tour.finale.text')}
        </p>
        <Button type="button" onClick={() => useTour.getState().stop()} className="mt-5 w-full">
          {t('tour.finale.button')}
        </Button>
      </motion.div>
    </div>
  );
}
