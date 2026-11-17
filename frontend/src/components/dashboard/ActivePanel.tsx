'use client';

import type { ReactNode } from 'react';
import type { Bill } from '@/types/api';
import { formatTotals, sortActive, totalsByCurrency } from '@/lib/utils/home';
import { useTranslation } from '@/lib/i18n/useTranslation';
import CollectingRow from './CollectingRow';
import OwingRow from './OwingRow';
import SettledRow from './SettledRow';
import { RowsCard, SectionHeading } from './RowParts';

/**
 * The open bills, by what the person has to do: collect from the others, pay
 * their own share, or nothing until the owner closes it.
 */
export default function ActivePanel({ bills, userId, empty, onRemind, onDelete, onMarkPaid, onSettled }: {
  bills: Bill[];
  userId: number;
  empty: ReactNode;
  onRemind: (bill: Bill) => Promise<void>;
  onDelete: (billId: number) => Promise<void>;
  onMarkPaid: (bill: Bill, paid: boolean) => Promise<void>;
  onSettled: (billId: number) => void;
}) {
  const { t } = useTranslation();
  if (bills.length === 0) return <>{empty}</>;

  const { collecting, owing, settled } = sortActive(bills, userId);
  const owedByMe = formatTotals(totalsByCurrency(owing, (bill) => bill.my_seat?.amount ?? 0));

  return (
    <div className="flex flex-col gap-7">
      {collecting.length > 0 && (
        <section>
          <SectionHeading title={t('home.collecting')} count={collecting.length} />
          <RowsCard>
            {collecting.map((bill) => (
              <CollectingRow key={bill.id} bill={bill} onRemind={onRemind} onDelete={onDelete} />
            ))}
          </RowsCard>
        </section>
      )}

      {owing.length > 0 && (
        <section>
          <SectionHeading title={t('home.owing')} total={owedByMe || undefined} />
          <div className="flex flex-col gap-3">
            {owing.map((bill) => (
              <OwingRow key={bill.id} bill={bill} onMarkPaid={onMarkPaid} onSettled={onSettled} />
            ))}
          </div>
        </section>
      )}

      {settled.length > 0 && (
        <section>
          <SectionHeading title={t('home.settled')} count={settled.length} />
          <RowsCard quiet>
            {settled.map((bill) => (
              <SettledRow key={bill.id} bill={bill} />
            ))}
          </RowsCard>
        </section>
      )}
    </div>
  );
}
