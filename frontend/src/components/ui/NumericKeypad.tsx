'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useIsPresent } from 'framer-motion';
import { Delete, ChevronDown } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { useScrollLock } from '@/hooks/useScrollLock';
import {
  evaluate,
  formatExpression,
  formatResult,
  hasBinaryOperator,
  collapseExpression,
} from '@/lib/utils/calc';

interface NumericKeypadProps {
  /** Up or down. Kept mounted by the caller so it can slide away as well. */
  open: boolean;
  /** Field label shown above the live value. */
  label: string;
  /** Current raw digit string (no separators), e.g. "52000". In calculator
   *  mode this is the in-progress expression, e.g. "52000+3000". */
  value: string;
  onChange: (next: string) => void;
  onClose: () => void;
  /** Small unit shown next to the value (e.g. "сум"). */
  unit?: string;
  /** Amount mode → a «000» key; otherwise an iOS-style dismiss key (people). */
  thousands?: boolean;
  /** Optional upper bound — entered values are clamped to it (e.g. headcount). */
  max?: number;
  /** Calculator mode: + − × ÷ operators, a decimal-point key (instead of «000»)
   *  and negative amounts. On close the expression collapses to its result. */
  calculator?: boolean;
}

const MAX_LEN = 12;
const MAX_EXPR_LEN = 40;
const MAX_DECIMALS = 2;

const groupDigits = (v: string) => v.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

const KEY =
  'flex items-center justify-center rounded-[11px] border-[1.5px] border-outline bg-surface py-[15px] font-mono text-[24px] font-bold text-foreground btn-hard-sm';
const OPKEY =
  'flex items-center justify-center rounded-[11px] border-[1.5px] border-outline bg-surface-2 py-2.5 font-mono text-[20px] font-bold text-foreground btn-hard-sm hover:border-accent hover:bg-accent hover:text-accent-fg';

const isOperator = (c: string) => c === '+' || c === '-' || c === '*' || c === '/';
const isNumberChar = (c: string) => (c >= '0' && c <= '9') || c === '.';

const lastBinaryOpIndex = (s: string) => {
  for (let i = s.length - 1; i >= 1; i--) {
    if (isOperator(s[i]) && isNumberChar(s[i - 1])) return i;
  }
  return -1;
};
const currentNumber = (s: string) => s.slice(lastBinaryOpIndex(s) + 1);

/**
 * In-app numeric keypad (Bold design `.kpsheet`) — a docked bottom sheet used
 * instead of the OS keyboard for headcount and amount inputs. In calculator
 * mode it grows an operators row and a decimal-point key. It slides up when
 * opened and back down when closed.
 */
export default function NumericKeypad({ open, ...sheet }: NumericKeypadProps) {
  if (typeof document === 'undefined') return null;
  // Drawn on <body>: a fixed sheet inside a transformed ancestor (the sliding
  // bill tabs) would be positioned against that ancestor, not the viewport.
  return createPortal(
    <AnimatePresence>{open && <KeypadSheet key="keypad" {...sheet} />}</AnimatePresence>,
    document.body,
  );
}

function KeypadSheet({
  label,
  value,
  onChange,
  onClose,
  unit,
  thousands,
  max,
  calculator,
}: Omit<NumericKeypadProps, 'open'>) {
  useScrollLock(true);
  // On its way down the pad takes no more keys or taps.
  const present = useIsPresent();

  // The tap that opens the keypad also lands on the backdrop once the layout
  // settles — most visibly when the OS keyboard was up for the name field and
  // collapses as the pad appears, closing it on the first digit. Arm the
  // tap-to-dismiss only after that has passed.
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    // Focus is also dropped so the OS keyboard goes away predictably.
    (document.activeElement as HTMLElement | null)?.blur();
    const id = setTimeout(() => setArmed(true), 350);
    return () => clearTimeout(id);
  }, []);

  const { t } = useTranslation();

  // Clamp typed values to an optional ceiling (e.g. a sane headcount) so a huge
  // number can't be entered and overflow the backend integer column.
  const clampMax = (v: string) => {
    if (max == null) return v;
    return parseInt(v || '0', 10) > max ? String(max) : v;
  };

  const pressDigit = (d: string) => {
    const next = value === '0' ? d : (value + d).slice(0, MAX_LEN);
    onChange(clampMax(next));
  };
  const pressThousands = () => {
    if (!value || value === '0') return;
    onChange(clampMax((value + '000').slice(0, MAX_LEN)));
  };
  const backspace = () => onChange(value.slice(0, -1));

  // ── calculator-mode input ────────────────────────────────────────────────
  const pressCalcDigit = (d: string) => {
    if (value.length >= MAX_EXPR_LEN) return;
    const cur = currentNumber(value);
    const dot = cur.indexOf('.');
    if (dot !== -1 && cur.length - dot - 1 >= MAX_DECIMALS) return;
    const digits = cur.replace('-', '');
    if (digits === '0') {
      onChange(value.slice(0, -1) + d);
      return;
    }
    if (dot === -1 && digits.length >= MAX_LEN) return;
    onChange(value + d);
  };

  const pressDot = () => {
    if (value.length >= MAX_EXPR_LEN) return;
    const cur = currentNumber(value);
    if (cur.includes('.')) return;
    onChange(cur === '' || cur === '-' ? value + '0.' : value + '.');
  };

  const pressOperator = (op: string) => {
    if (value === '') {
      if (op === '-') onChange('-');
      return;
    }
    if (value === '-') return;
    const last = value[value.length - 1];
    if (isOperator(last)) {
      onChange(value.slice(0, -1) + op);
      return;
    }
    const base = last === '.' ? value.slice(0, -1) : value;
    onChange(base + op);
  };

  const commit = () => {
    onChange(collapseExpression(value));
    onClose();
  };

  // ── display ──────────────────────────────────────────────────────────────
  const close = calculator ? commit : onClose;

  // A desktop client has a real keyboard, and typing is the obvious thing to try
  // once the pad has taken over the field. Phones are untouched: there are no
  // keydown events to catch there, so nothing summons the OS keyboard.
  //
  // The listener sits on the document because opening the pad blurs whatever was
  // focused; the input guard covers the case where something took focus back, so
  // digits keep going to that field rather than here. No dependency list — the
  // handler has to read the current expression, which changes on every keystroke.
  //
  // Capture phase, and the keys the pad takes stop there: the sheet the pad
  // sits in closes itself on Escape from the same document, and a key meant
  // for the pad must not also throw away the form behind it.
  useEffect(() => {
    if (!present) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target?.tagName === 'INPUT' ||
        target?.tagName === 'TEXTAREA' ||
        target?.isContentEditable
      ) {
        return;
      }

      const { key } = event;
      if (key >= '0' && key <= '9') {
        if (calculator) pressCalcDigit(key);
        else pressDigit(key);
      } else if (key === 'Backspace') {
        backspace();
      } else if (key === 'Enter' || key === 'Escape') {
        close();
      } else if (calculator && (key === '.' || key === ',')) {
        pressDot();
      } else if (calculator && isOperator(key)) {
        pressOperator(key);
      } else {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    };

    document.addEventListener('keydown', handleKey, true);
    return () => document.removeEventListener('keydown', handleKey, true);
  });

  let bigText: string;
  let exprLine: string | null = null;
  if (calculator) {
    if (hasBinaryOperator(value)) {
      const preview = evaluate(value);
      exprLine = formatExpression(value);
      bigText = preview != null ? formatResult(preview) : '—';
    } else {
      bigText = value ? formatExpression(value) : '0';
    }
  } else {
    bigText = thousands ? groupDigits(value || '0') : value || '0';
  }

  return (
    <>
      {/* Tap-outside to dismiss. */}
      {present && <div className="fixed inset-0 z-[59]" onClick={() => armed && close()} />}
      <motion.div
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        exit={{ y: '100%' }}
        transition={{ type: 'spring', stiffness: 380, damping: 34 }}
        className={`fixed inset-x-0 bottom-0 z-[60] ${present ? '' : 'pointer-events-none'} rounded-t-[20px] border-t-2 border-outline bg-surface pb-[calc(1.25rem+var(--content-safe-bottom))] pl-[calc(1rem+var(--content-safe-left))] pr-[calc(1rem+var(--content-safe-right))] pt-3.5 shadow-[0_-12px_34px_rgba(27,24,19,0.22)] dark:shadow-[0_-12px_34px_rgba(0,0,0,0.5)]`}
      >
        <div className="mx-auto mb-3 h-[5px] w-[42px] rounded-full bg-border" />

        <div className="mb-3.5 flex items-end justify-between gap-3 px-0.5">
          <div className="min-w-0">
            <div className="mb-1.5 font-display text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
              {label}
            </div>
            {exprLine && (
              <div className="mb-0.5 truncate font-mono text-[13px] text-muted-2">{exprLine}</div>
            )}
            <div className="font-mono text-[30px] font-bold leading-none text-foreground">
              {bigText}
              {unit && <span className="ml-1 text-[16px] text-muted-2">{unit}</span>}
              <span className="ml-[3px] inline-block h-[26px] w-[2px] -translate-y-[4px] animate-pulse bg-accent align-[-4px]" />
            </div>
          </div>
          <button
            type="button"
            onClick={close}
            className="flex-shrink-0 rounded-lg border-[1.5px] border-outline bg-accent px-4 py-2.5 font-display text-[12px] font-bold uppercase tracking-[0.04em] text-accent-fg btn-hard-sm"
          >
            {t('common.done')}
          </button>
        </div>

        {calculator && (
          <div className="mb-[11px] grid grid-cols-5 gap-[9px]">
            {(
              [
                ['+', '+'],
                ['−', '-'],
                ['×', '*'],
                ['÷', '/'],
              ] as const
            ).map(([glyph, op]) => (
              <button key={op} type="button" onClick={() => pressOperator(op)} className={OPKEY}>
                {glyph}
              </button>
            ))}
            <button
              type="button"
              onClick={commit}
              aria-label={t('common.done')}
              className={`${OPKEY} bg-surface text-muted-2 hover:border-outline hover:bg-surface-2 hover:text-foreground`}
            >
              <ChevronDown className="h-5 w-5" />
            </button>
          </div>
        )}

        <div className="grid grid-cols-3 gap-[9px]">
          {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => (calculator ? pressCalcDigit(d) : pressDigit(d))}
              className={KEY}
            >
              {d}
            </button>
          ))}
          {calculator ? (
            <button
              type="button"
              onClick={pressDot}
              aria-label="."
              className={`${KEY} text-[30px] leading-none`}
            >
              •
            </button>
          ) : thousands ? (
            <button
              type="button"
              onClick={pressThousands}
              className={`${KEY} text-[13px] text-muted`}
            >
              000
            </button>
          ) : (
            <button
              type="button"
              onClick={onClose}
              aria-label={t('common.done')}
              className={`${KEY} text-muted`}
            >
              <ChevronDown className="h-[22px] w-[22px]" />
            </button>
          )}
          <button
            type="button"
            onClick={() => (calculator ? pressCalcDigit('0') : pressDigit('0'))}
            className={KEY}
          >
            0
          </button>
          <button
            type="button"
            onClick={backspace}
            aria-label={t('common.delete')}
            className={`${KEY} bg-surface-2`}
          >
            <Delete className="h-[22px] w-[22px]" />
          </button>
        </div>
      </motion.div>
    </>
  );
}
