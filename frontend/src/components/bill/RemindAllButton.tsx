'use client';

import { Bell, BellRing, Lock } from 'lucide-react';
import ProCorner from '@/components/pro/ProCorner';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';

// Where the time left goes in «Remind again in {left}», in any language's word order.
const TIME_SLOT = '\u2063';

/**
 * «Remind everyone» — one press that gets the money in, so it stands out: the
 * accent while there is someone to remind, with how many; quiet once everyone
 * has just been reminded, counting down to when it may be pressed again; and
 * without Pro a lock, with Pro's stamp on its corner — pressing it then opens
 * the paywall. With nobody to remind and nobody to wait for, it stays in place,
 * quiet, and a press says what to do first.
 */
export default function RemindAllButton({ label, ready, wait, hint, busy, locked, onPress, className = '' }: {
  label: string;
  /** How many people a press would remind now. */
  ready: number;
  /** With nobody to remind now: the time left until somebody may be, «59:07». */
  wait?: string;
  /** With nobody to remind and nobody to wait for: what to do first, said on a
   *  press — before the paywall, which would sell what cannot be done yet. */
  hint?: string;
  busy: boolean;
  locked: boolean;
  onPress: () => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const active = ready > 0;
  const why = active || wait ? undefined : hint;
  const Icon = locked ? Lock : active || why ? Bell : BellRing;
  const [beforeTime, afterTime = ''] = t('bill.remindAgainIn', { left: TIME_SLOT }).split(TIME_SLOT);
  return (
    <button
      type="button"
      onClick={why ? () => showToast(why, 'info') : onPress}
      disabled={busy || (!active && !why)}
      aria-disabled={why ? true : undefined}
      className={`btn-hard-sm relative flex min-h-12 w-full items-center justify-center gap-2 rounded-lg border-[1.5px] border-outline px-3 py-2 font-display text-[14px] font-extrabold disabled:cursor-not-allowed aria-disabled:cursor-not-allowed ${
        active ? 'bg-accent text-accent-fg disabled:opacity-70' : 'bg-surface text-muted'
      } ${className}`}
    >
      <Icon aria-hidden="true" className="h-[18px] w-[18px] shrink-0" strokeWidth={2.25} />
      {!active && wait ? (
        <span className="min-w-0 break-words">
          {beforeTime}
          <span className="inline-block rounded-[4px] bg-surface-2 px-1.5 font-mono text-[13px] leading-5 tabular-nums text-foreground">
            {wait}
          </span>
          {afterTime}
        </span>
      ) : (
        <span className="min-w-0 break-words">{label}</span>
      )}
      {active && !locked && (
        <span className="shrink-0 rounded-[4px] bg-accent-fg px-1.5 font-mono text-[12px] leading-5 text-accent">{ready}</span>
      )}
      {locked && <ProCorner />}
    </button>
  );
}
