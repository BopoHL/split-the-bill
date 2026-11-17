'use client';

import { Bell, BellOff, BellRing, Lock } from 'lucide-react';
import ChipButton from '@/components/ui/ChipButton';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { shortDuration, sinceLabel, type ReminderState } from '@/lib/utils/reminders';
import { useProGate } from '@/lib/store/usePro';
import ProCorner from '@/components/pro/ProCorner';

type Translate = (path: string, params?: Record<string, string>) => string;

/** The owner's reminder to one seat: send one, or what became of the last. */
export default function RemindChip({ state, now, busy, onRemind }: {
  state: ReminderState;
  now: Date;
  busy: boolean;
  onRemind: () => void;
}) {
  const { t } = useTranslation();
  const { locked, gated } = useProGate('reminders');

  if (state.kind === 'ready') {
    return (
      <ChipButton icon={locked ? Lock : Bell} onClick={gated(onRemind)} disabled={busy} className={locked ? 'relative' : ''}>
        {state.lastFailed ? t('bill.remindAgain') : t('bill.remind')}
        {locked && <ProCorner />}
      </ChipButton>
    );
  }
  if (state.kind === 'sending') {
    return <ChipButton icon={Bell} disabled>{t('bill.remindSending')}</ChipButton>;
  }
  if (state.kind === 'reminded') {
    return <ChipButton icon={BellRing} disabled>{t('bill.reminded', { since: sinceLabel(state.at, now, t) })}</ChipButton>;
  }
  return <ChipButton icon={BellOff} disabled>{t('bill.remindNotDelivered')}</ChipButton>;
}

/** The line under the seat's buttons that explains the chip, when it needs it. */
export function remindHint(state: ReminderState, now: Date, t: Translate): string | null {
  if (state.kind === 'ready') return state.lastFailed ? t('bill.remindLastFailed') : null;
  if (state.kind === 'reminded') {
    return t('bill.remindNextIn', { left: shortDuration(state.nextAt.getTime() - now.getTime(), t) });
  }
  if (state.kind === 'unreachable') {
    return t('bill.remindUnreachable', { left: shortDuration(state.nextAt.getTime() - now.getTime(), t) });
  }
  return null;
}
