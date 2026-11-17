'use client';

import { useCallback, useEffect, useState } from 'react';
import type { OwedSummary } from '@/types/api';
import { getOwed, remindEveryoneWhoOwes } from '@/lib/api/reminders';
import { formatCurrency } from '@/lib/utils/currency';
import { peopleUnit } from '@/lib/utils/plural';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { remindersLeft, useProGate } from '@/lib/store/usePro';
import RemindAllButton from '@/components/bill/RemindAllButton';
import { useNow } from '@/hooks/useNow';
import { countdown } from '@/lib/utils/reminders';

/**
 * What others owe the user across all their open bills, above the bills
 * themselves, with one press to remind every one of them — and, once all of
 * them have just been reminded, a countdown to when it may be pressed again.
 * While nobody owes it stays, quiet, and a press says what to do first.
 */
export default function OwedCard({ userId, refreshKey = 0, onReminded }: {
  userId: number;
  /** Bumped when something on the page may have changed what is owed. */
  refreshKey?: number;
  onReminded?: () => void;
}) {
  const { t, language } = useTranslation();
  const [owed, setOwed] = useState<OwedSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const { locked, gated } = useProGate('reminders', remindersLeft);

  const load = useCallback(async () => {
    try {
      setOwed(await getOwed(userId));
    } catch (error) {
      console.error('Error loading what is owed:', error);
    }
  }, [userId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const nextAt = owed?.next_reminder_at ? Date.parse(owed.next_reminder_at) : null;
  const now = useNow(nextAt);
  const waitMs = nextAt === null ? 0 : nextAt - now.getTime();
  const due = nextAt !== null && waitMs <= 0;

  // The hour is over: ask who may be reminded now.
  useEffect(() => {
    if (due) void load();
  }, [due, load]);

  if (!owed) return null;

  const remind = async () => {
    setBusy(true);
    try {
      const { queued } = await remindEveryoneWhoOwes(userId);
      track(AnalyticsEvent.RemindersSent, { scope: 'all_bills', from: 'home', queued });
      showToast(queued > 0 ? t('bill.remindQueued', { count: String(queued) }) : t('bill.remindNobody'), queued > 0 ? 'success' : 'error');
      await load();
      onReminded?.();
    } catch (error) {
      console.error(error);
      showToast(t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-label={t('home.owedTitle')}
      className="mb-5 rounded-lg border-[1.5px] border-outline bg-surface p-3.5 shadow-[var(--shadow-hard)]"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-[11px] font-bold uppercase tracking-[0.14em] text-muted">{t('home.owedTitle')}</h2>
        {owed.people > 0 && (
          <span className="shrink-0 font-mono text-[12px] text-muted">
            {owed.people} {peopleUnit(owed.people, language)}
          </span>
        )}
      </div>
      <div className="mt-1 flex flex-col">
        {owed.people === 0 ? (
          <span className="font-display text-[20px] font-bold leading-tight text-muted">{t('home.owedNobody')}</span>
        ) : (
          owed.totals.map((total) => (
            <span key={total.currency} className="font-mono text-[24px] font-bold leading-tight tabular-nums text-foreground">
              {formatCurrency(total.amount, total.currency)}
            </span>
          ))
        )}
      </div>
      <RemindAllButton
        className="mt-3"
        label={owed.remindable > 0 || owed.why_nobody ? t('home.remindEveryone') : t('home.remindEveryoneDone')}
        ready={owed.remindable}
        wait={waitMs > 0 ? countdown(waitMs) : undefined}
        hint={owed.why_nobody ? t(`bill.whyNobody.${owed.why_nobody}`) : undefined}
        busy={busy}
        locked={locked}
        onPress={gated(remind)}
      />
    </section>
  );
}
