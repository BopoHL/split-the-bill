'use client';

import type { Bill } from '@/types/api';
import { useTranslation } from '@/lib/i18n/useTranslation';

const MAX_SEGMENTS = 5;

/**
 * «1/3 paid» with a segment per payer, for the owner's open bill. The owner is
 * left out on both sides: it answers how many of the others have paid them.
 */
export default function PaidProgress({ bill }: { bill: Bill }) {
  const { t } = useTranslation();
  const paid = bill.payers_paid ?? 0;
  // The headcount declared at creation minus the owner, or who actually joined
  // for bills made before it was asked.
  const expected = bill.expected_people != null
    ? Math.max(bill.expected_people - 1, bill.payers_count ?? 0)
    : bill.payers_count ?? 0;
  const segments = Math.min(Math.max(expected, paid), MAX_SEGMENTS);

  return (
    <span className="flex items-center gap-2">
      <span className="flex items-center gap-[3px]" aria-hidden>
        {Array.from({ length: segments }).map((_, index) => (
          <span
            key={index}
            className={`h-[7px] w-3 rounded-[2px] border-[1.2px] ${index < paid ? 'border-success bg-success' : 'border-outline'}`}
          />
        ))}
      </span>
      <span className="font-mono text-[11px] text-muted">
        <b className="font-bold text-foreground">{paid}</b>/{expected} {t('home.paid')}
      </span>
    </span>
  );
}
