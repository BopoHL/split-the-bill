'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Minus, Plus } from 'lucide-react';
import { peopleUnit } from '@/lib/utils/plural';
import { MAX_PEOPLE } from '@/lib/constants';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { hapticFeedback } from '@/lib/telegram/init';
import { TourAnchor } from '@/lib/tour/anchors';
import {
  ORDERED_CURRENCIES,
  currencySymbolFor,
  type Currency,
} from '@/lib/utils/currency';

const STEP_KEY =
  'btn-hard flex w-[58px] flex-shrink-0 items-center justify-center rounded-[9px] border-[1.5px] border-outline bg-surface text-foreground hover:bg-accent hover:text-accent-fg';

interface StepPeopleProps {
  value: string;
  onChange: (next: string) => void;
  onOpenKeypad: () => void;
  invalid: boolean;
  currency: Currency;
  onCurrencyChange: (next: Currency) => void;
}

/**
 * Step 1 — how many people are on the bill.
 *
 * It comes first because it decides the shape of everything after it: the bill
 * is created with a seat per person, and dishes can be put on those seats before
 * anyone joins.
 */
export default function StepPeople({
  value,
  onChange,
  onOpenKeypad,
  invalid,
  currency,
  onCurrencyChange,
}: StepPeopleProps) {
  const { t, language } = useTranslation();

  const parsed = parseInt(value, 10);
  const valid = !isNaN(parsed) && parsed >= 1 && parsed <= MAX_PEOPLE;

  const adjust = (delta: number) => {
    const next = Math.min(MAX_PEOPLE, Math.max(1, (isNaN(parsed) ? 0 : parsed) + delta));
    // A tap the hand feels too, as long as it changed something: at 1 or at
    // the limit the key presses but the count stays put.
    if (next !== parsed) hapticFeedback('light');
    onChange(String(next));
  };

  return (
    <div>
      <label className="mb-1.5 block font-display text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
        {t('bill.peopleCount')}
      </label>
      {/* Three keys side by side rather than one block: each has its own hard
          shadow to sink into, so a tap on − or + is felt. */}
      <div className="flex items-stretch gap-2.5">
        <button type="button" onClick={() => adjust(-1)} aria-label="−" data-tour={TourAnchor.PeopleLess} className={STEP_KEY}>
          <Minus className="h-[22px] w-[22px]" />
        </button>
        <button
          type="button"
          onClick={onOpenKeypad}
          className={`btn-hard flex flex-1 flex-col items-center justify-center rounded-[9px] border-[1.5px] bg-background py-3 ${
            invalid ? 'border-danger' : 'border-outline'
          }`}
        >
          <span className="font-mono text-[26px] font-bold leading-none text-foreground">
            {value || '0'}
          </span>
          <span className="mt-[3px] font-display text-[10px] font-bold uppercase tracking-[0.1em] text-muted-2">
            {peopleUnit(valid ? parsed : 0, language)}
          </span>
        </button>
        <button type="button" onClick={() => adjust(1)} aria-label="+" data-tour={TourAnchor.PeopleMore} className={STEP_KEY}>
          <Plus className="h-[22px] w-[22px]" />
        </button>
      </div>
      {invalid && (
        <p className="mt-1.5 text-xs font-medium text-danger">{t('bill.peopleCountRequired')}</p>
      )}

      <label className="mb-1.5 mt-4 block font-display text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
        {t('bill.billCurrency')}
      </label>
      <CurrencyPicker value={currency} onChange={onCurrencyChange} language={language} />
    </div>
  );
}

/** How tall the open currency list may get, and the breathing room it keeps
 *  from the edge it drops toward. */
const LIST_MAX_PX = 224;
const LIST_MIN_PX = 132;
const LIST_GUTTER_PX = 12;
const LIST_OFFSET_PX = 6;

interface ListPlacement {
  up: boolean;
  maxHeight: number;
  left: number;
  width: number;
  /** Distance from the viewport edge the list grows away from. */
  edge: number;
}

/** Where the list fits: under the trigger unless that would be cramped and
 *  there is more room above — the picker sits low in the step, so on a short
 *  screen the room is usually over it. */
export function placeList(trigger: DOMRect, viewportHeight: number): ListPlacement {
  const below = viewportHeight - trigger.bottom - LIST_GUTTER_PX;
  const above = trigger.top - LIST_GUTTER_PX;
  const up = below < LIST_MIN_PX && above > below;
  return {
    up,
    maxHeight: Math.max(LIST_MIN_PX, Math.min(LIST_MAX_PX, up ? above : below)),
    left: trigger.left,
    width: trigger.width,
    edge: up ? viewportHeight - trigger.top + LIST_OFFSET_PX : trigger.bottom + LIST_OFFSET_PX,
  };
}

/**
 * Which money the bill is counted in.
 *
 * Asked here rather than left to the settings screen: it is the one thing that
 * can't be corrected later without re-reading every amount, and the person who
 * is about to type them in is the one who knows.
 */
function CurrencyPicker({
  value,
  onChange,
  language,
}: {
  value: Currency;
  onChange: (next: Currency) => void;
  language: string;
}) {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // The list is drawn on the body, fixed to the viewport, and bounded to the
  // room actually there. Eighteen currencies are taller than the create sheet,
  // and a list positioned inside it — even absolutely — counted toward the
  // scroll height of the sheet's body, so opening it scrolled the whole step.
  // Out on the body it scrolls only within itself.
  const [placement, setPlacement] = useState<ListPlacement | null>(null);

  // Measured on the way open, when the trigger's position is known and before
  // anything is painted — rather than after, which would flash a full-height
  // list and scroll the sheet under it.
  const toggle = () => {
    if (open) {
      setOpen(false);
      return;
    }
    const trigger = boxRef.current?.getBoundingClientRect();
    if (trigger) setPlacement(placeList(trigger, window.innerHeight));
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (boxRef.current?.contains(target) || listRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutside);
    return () => document.removeEventListener('mousedown', closeOnOutside);
  }, [open]);

  const current = ORDERED_CURRENCIES.find((c) => c.code === value);

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center gap-2.5 rounded-[9px] border-[1.5px] border-outline bg-background px-3.5 py-3 text-left"
      >
        <span className="text-[20px] leading-none">{current?.flag}</span>
        <span className="font-mono text-[13px] font-bold uppercase tracking-[0.06em] text-foreground">
          {current?.ticker ?? value}
        </span>
        <span className="font-mono text-[12px] text-muted-2">
          {currencySymbolFor(value, language)}
        </span>
        <ChevronDown className="ml-auto h-4 w-4 text-muted-2" />
      </button>

      {open && placement && createPortal(
        <div
          ref={listRef}
          style={{
            maxHeight: placement.maxHeight,
            left: placement.left,
            width: placement.width,
            ...(placement.up ? { bottom: placement.edge } : { top: placement.edge }),
          }}
          className="fixed z-[60] overflow-y-auto overscroll-contain rounded-lg border-[1.5px] border-outline bg-surface p-1 shadow-[var(--shadow-lifted)]"
        >
          {ORDERED_CURRENCIES.map((option) => (
            <button
              key={option.code}
              type="button"
              onClick={() => {
                onChange(option.code);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-surface-2"
            >
              <span className="text-[18px] leading-none">{option.flag}</span>
              <span className="font-mono text-[12px] font-bold uppercase tracking-[0.06em] text-foreground">
                {option.ticker}
              </span>
              <span className="font-mono text-[11px] text-muted-2">
                {currencySymbolFor(option.code, language)}
              </span>
              {option.code === value && <Check className="ml-auto h-4 w-4 text-accent" />}
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
}
