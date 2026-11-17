'use client';

import { useId, useRef } from 'react';
import { X } from 'lucide-react';
import type { PaymentChoice } from '@/hooks/usePaymentChoice';
import { cardBrand, displayDetails } from '@/lib/utils/paymentDetails';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { TourAnchor } from '@/lib/tour/anchors';

const LABEL = 'font-display text-[10px] font-bold uppercase tracking-[0.12em] text-muted';
const ROW = 'flex min-h-11 items-center gap-2.5 px-3 py-2';
// Drawn rather than native, so it reads the same in both themes: an outlined
// ring, filled with the accent round a dot of the page when picked.
const RADIO = 'h-5 w-5 shrink-0 cursor-pointer appearance-none rounded-full border-[1.5px] border-outline bg-background checked:border-accent checked:bg-accent checked:shadow-[inset_0_0_0_4px_var(--background)]';

function Brand({ details }: { details: string }) {
  const brand = cardBrand(details);
  if (!brand) return null;
  return (
    <span className="shrink-0 rounded-[4px] border-[1.5px] border-outline bg-surface-2 px-1.5 py-[3px] font-display text-[9.5px] font-extrabold leading-none tracking-[0.08em] text-foreground">
      {brand}
    </span>
  );
}

/**
 * Where the money goes, as one choice: a saved card, or «another card» typed
 * in. With nothing saved yet it is only the field. Saved cards are shown in
 * full, since they are the owner's own, each with its cross to remove it.
 */
export default function PaymentDetailsChooser({ choice, label, shortList = false }: {
  choice: PaymentChoice;
  /** What the choice is for; the saved cards are «Your cards» without one. */
  label?: string;
  /** Three rows of saved cards, then scrolling: for a host that must not grow. */
  shortList?: boolean;
}) {
  const { t } = useTranslation();
  const name = useId();
  const input = useRef<HTMLInputElement>(null);
  const { methods } = choice;

  const field = (
    <div className="flex flex-col gap-2">
      <div data-tour={TourAnchor.CardField} className="flex min-h-[50px] items-center gap-2 rounded-[9px] border-[1.5px] border-outline bg-background px-3.5 focus-within:border-accent">
        <input
          ref={input}
          value={choice.draft}
          onChange={(event) => choice.changeDraft(event.target.value)}
          inputMode="tel"
          autoComplete="off"
          enterKeyHint="done"
          placeholder="0000 0000 0000 0000"
          aria-label={t('bill.cardNumber')}
          className="min-w-0 flex-1 bg-transparent py-3 font-mono text-[16px] font-bold tracking-[0.02em] text-foreground outline-none placeholder:font-medium placeholder:text-muted-2"
        />
        <Brand details={choice.draft} />
      </div>
      <label className="flex items-center gap-2 text-[12.5px] text-muted">
        <input
          type="checkbox"
          checked={choice.remember}
          onChange={(event) => choice.setRemember(event.target.checked)}
          className="h-[18px] w-[18px] shrink-0 accent-success"
        />
        {t('bill.rememberCard')}
      </label>
    </div>
  );

  if (!choice.ready) {
    return (
      <div data-tour={TourAnchor.PaymentChooser} className="flex flex-col gap-1.5">
        {label && <span className={LABEL}>{label}</span>}
        <div aria-busy="true" className="h-[50px] animate-pulse rounded-[9px] border-[1.5px] border-border bg-surface-2" />
      </div>
    );
  }

  if (methods.length === 0) {
    return (
      <div data-tour={TourAnchor.PaymentChooser} className="flex flex-col gap-1.5">
        {label && <span className={LABEL}>{label}</span>}
        {field}
      </div>
    );
  }

  return (
    <div data-tour={TourAnchor.PaymentChooser} className="flex flex-col gap-1.5">
      <span className={LABEL}>{label ?? t('bill.yourCards')}</span>
      <div role="radiogroup" aria-label={t('bill.yourCards')} className="overflow-hidden rounded-[10px] border-[1.5px] border-outline bg-surface shadow-[var(--shadow-hard-sm)]">
        <div className={`${shortList ? 'max-h-[8.5rem]' : 'max-h-[min(36dvh,16rem)]'} overflow-y-auto overscroll-contain`}>
          {methods.map((method) => {
            const picked = method.id === choice.selectedId;
            return (
              <div key={method.id} className={`border-b-[1.5px] border-dashed border-border ${picked ? 'bg-accent-weak' : ''}`}>
                <label className={`${ROW} cursor-pointer`}>
                  <input
                    type="radio"
                    name={name}
                    checked={picked}
                    onChange={() => choice.select(method)}
                    className={RADIO}
                  />
                  <Brand details={method.value} />
                  <span className="min-w-0 flex-1 truncate font-mono text-[14px] font-bold text-foreground">
                    {method.label ? `${method.label} — ${displayDetails(method.value)}` : displayDetails(method.value)}
                  </span>
                  <button
                    type="button"
                    onClick={() => choice.remove(method)}
                    aria-label={`${t('common.delete')}: ${displayDetails(method.value)}`}
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border-[1.5px] border-danger text-danger"
                  >
                    <X className="h-4 w-4" strokeWidth={2.5} />
                  </button>
                </label>
              </div>
            );
          })}
        </div>
        <div className={choice.isNew ? 'bg-accent-weak' : ''}>
          <label className={`${ROW} cursor-pointer font-display text-[14px] font-extrabold text-foreground`}>
            <input
              type="radio"
              name={name}
              checked={choice.isNew}
              onChange={() => {
                choice.chooseNew();
                requestAnimationFrame(() => input.current?.focus());
              }}
              className={RADIO}
            />
            {t('bill.otherCard')}
          </label>
          {choice.isNew && <div className="px-3 pb-3">{field}</div>}
        </div>
      </div>
    </div>
  );
}
