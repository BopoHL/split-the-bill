'use client';

import type { ReactNode } from 'react';
import type { BillDetail, BillParticipant } from '@/types/api';
import { sortParticipantsSelfFirst } from '@/lib/utils/participants';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { TourAnchor } from '@/lib/tour/anchors';

const DASHED_RULE = { backgroundImage: 'repeating-linear-gradient(90deg, var(--border) 0 5px, transparent 5px 9px)' };

/**
 * The people on a bill as one ticket: the viewer's own seat first, with the
 * payment progress in the header.
 */
export default function ParticipantList({ bill, currentUserId, headcount, renderRow, children }: {
  bill: BillDetail;
  currentUserId?: number;
  /** Replaces the plain seat count — the owner's editor goes here. */
  headcount?: ReactNode;
  renderRow: (participant: BillParticipant) => ReactNode;
  /** Rendered under the ticket, such as leaving the bill. */
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  const rows = sortParticipantsSelfFirst(bill.participants, currentUserId);
  // Every seat but the owner's owes the owner, whether or not anyone has
  // claimed it or been given a dish yet.
  const payers = bill.participants.filter((participant) => participant.user_id !== bill.owner_id);
  const paidCount = payers.filter((participant) => participant.is_paid).length;
  const everyonePaid = payers.length > 0 && paidCount === payers.length;

  return (
    <div>
      <div className="mx-0.5 mb-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 font-display text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
        <span>{t('bill.participants')}</span>
        {headcount ?? (
          <span className="font-mono text-[12px] tracking-normal text-foreground">
            {bill.participants.length}
          </span>
        )}
        <span aria-hidden="true" className="h-[1.5px] min-w-4 flex-1" style={DASHED_RULE} />
        {payers.length > 0 && (
          <span data-testid="paid-progress" className={everyonePaid ? 'text-success' : undefined}>
            {t('bill.paidProgress')}{' '}
            <span className={`font-mono text-[12px] tracking-normal ${everyonePaid ? '' : 'text-foreground'}`}>
              {paidCount}/{payers.length}
            </span>
          </span>
        )}
      </div>

      <ul data-tour={TourAnchor.Participants} className="rounded-lg border-[1.5px] border-outline bg-surface shadow-[var(--shadow-hard)]">
        {rows.map((participant, index) => (
          <li
            key={participant.id}
            className={`first:rounded-t-[7px] last:rounded-b-[7px] ${index > 0 ? 'border-t-[1.5px] border-dashed border-border' : ''}`}
          >
            {renderRow(participant)}
          </li>
        ))}
      </ul>

      {children}
    </div>
  );
}
