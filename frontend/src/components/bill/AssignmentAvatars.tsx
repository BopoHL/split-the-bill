'use client';

import type { BillParticipant } from '@/types/api';
import { participantInitial, participantLabel } from '@/lib/utils/participants';
import { useTranslation } from '@/lib/i18n/useTranslation';

export default function AssignmentAvatars({ participants }: { participants: BillParticipant[] }) {
  const { t } = useTranslation();
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-1" aria-label={participants.map((p) => participantLabel(p, t)).join(', ')}>
      {participants.map((p) => (
        <span key={p.id} title={participantLabel(p, t)} className="flex h-[26px] w-[26px] shrink-0 items-center justify-center overflow-hidden rounded-[5px] border-[1.5px] border-outline bg-surface font-display text-[11px] font-bold text-foreground shadow-[var(--shadow-hard-sm)]">
          {p.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={p.avatar_url} alt={participantLabel(p, t)} className="h-full w-full object-cover" />
          ) : participantInitial(p, t)}
        </span>
      ))}
    </span>
  );
}

/** The empty place a dish nobody has taken yet shows instead of avatars. */
export function FreeSeat() {
  const { t } = useTranslation();
  return <span role="img" aria-label={t('bill.unassigned')} title={t('bill.unassigned')} className="h-[26px] w-[26px] shrink-0 rounded-[5px] border-[1.5px] border-dashed border-muted-2" />;
}
