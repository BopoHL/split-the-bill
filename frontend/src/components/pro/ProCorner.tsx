'use client';

import { Star } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';

/** Pro's stamp on the corner of something only Pro does — in the gold of the
 *  Stars it is paid in, so it reads on any button in any theme. The control
 *  it sits on needs `relative`. */
export default function ProCorner() {
  const { t } = useTranslation();
  return (
    <>
      <span className="sr-only">{t('pro.locked')}</span>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -right-2 -top-2.5 z-[1] inline-flex h-5 rotate-[6deg] items-center gap-0.5 rounded-[5px] border-[1.5px] border-outline bg-star px-1.5 font-display text-[9px] font-extrabold uppercase leading-none tracking-[0.08em] text-star-fg shadow-[var(--shadow-hard-sm)]"
      >
        <Star className="h-2.5 w-2.5 fill-current" strokeWidth={2.5} />
        Pro
      </span>
    </>
  );
}
