'use client';

import { Star } from 'lucide-react';
import { useIsPro, usePro } from '@/lib/store/usePro';
import { useTranslation } from '@/lib/i18n/useTranslation';

/**
 * Pro in the header, by the profile — a stamp in the gold of the Stars it is
 * paid in, which reads on the header's ink in every theme. Without Pro it is
 * the gold itself, pressed into the bar like a coin: the way to it. With Pro
 * it is the gold outline: how long it lasts, and the way to extend it.
 */
export default function ProButton() {
  const { t } = useTranslation();
  const isPro = useIsPro();
  const openPaywall = usePro((state) => state.openPaywall);

  return (
    <button
      type="button"
      onClick={() => openPaywall()}
      aria-label={t(isPro ? 'pro.title' : 'pro.getPro')}
      className={`flex h-9 shrink-0 items-center gap-1 rounded-md border-[1.5px] px-2.5 font-display text-[11px] font-extrabold uppercase leading-none tracking-[0.12em] transition-[transform,box-shadow] duration-150 active:translate-x-[2px] active:translate-y-[2px] active:shadow-none ${
        isPro
          ? 'border-star text-star shadow-[2px_2px_0_color-mix(in_oklab,var(--star)_35%,var(--bar))]'
          : 'border-star-fg bg-star text-star-fg shadow-[2px_2px_0_color-mix(in_oklab,var(--star)_45%,var(--bar))]'
      }`}
    >
      <Star aria-hidden="true" className="h-3.5 w-3.5 fill-current" strokeWidth={2.25} />
      Pro
    </button>
  );
}
