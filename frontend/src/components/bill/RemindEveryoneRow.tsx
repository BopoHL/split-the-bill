'use client';

import { useState } from 'react';
import type { BillDetail } from '@/types/api';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { canBeReminded, countdown, latestOf, reminderState, whyNobody } from '@/lib/utils/reminders';
import { useNow } from '@/hooks/useNow';
import { remindersLeft, useProGate } from '@/lib/store/usePro';
import RemindAllButton from './RemindAllButton';

/**
 * Owner: one press reminds everyone who joined and has not paid yet. It sits
 * under the invite, at the head of the list it acts on, and counts down to
 * when it can be pressed again once everyone has had their reminder. With
 * nobody to remind it stays, quiet, and a press says what to do first.
 */
export default function RemindEveryoneRow({ bill, onRemindEveryone }: {
  bill: BillDetail;
  onRemindEveryone: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const { locked, gated } = useProGate('reminders', remindersLeft);

  const reminders = bill.participants
    .filter((participant) => canBeReminded(bill, participant))
    .map((participant) => participant.reminder);
  // Ticks while anyone is held, so the button wakes up by itself.
  const now = useNow(latestOf(reminders.map((reminder) => reminder?.next_at)));
  const states = reminders.map((reminder) => reminderState(reminder, now));

  const ready = states.filter((state) => state.kind === 'ready').length;
  const sending = states.some((state) => state.kind === 'sending');
  const nextAt = Math.min(
    ...states.flatMap((state) => (state.kind === 'reminded' || state.kind === 'unreachable' ? [state.nextAt.getTime()] : [])),
  );

  const press = async () => {
    setBusy(true);
    try {
      await onRemindEveryone();
    } finally {
      setBusy(false);
    }
  };

  const nobody = states.length === 0;
  const label = ready > 0 || nobody ? t('bill.remindAll') : sending ? t('bill.remindAllSending') : t('home.remindEveryoneDone');
  const wait = ready === 0 && !sending && Number.isFinite(nextAt) ? countdown(nextAt - now.getTime()) : undefined;

  return (
    <RemindAllButton
      className="mb-5"
      label={label}
      ready={ready}
      wait={wait}
      hint={nobody ? t(`bill.whyNobody.${whyNobody(bill)}`) : undefined}
      busy={busy}
      locked={locked}
      onPress={gated(press)}
    />
  );
}
