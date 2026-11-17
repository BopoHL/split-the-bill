'use client';

import { useMemo } from 'react';
import { SplitType, type BillDetail, type BillParticipant } from '@/types/api';
import { dishCount, dishEaters, tableSplit } from '@/lib/utils/itemSplit';
import { formatCurrency } from '@/lib/utils/currency';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface PositionLine {
  itemId: number;
  name: string;
  /** How many of the line's dishes they are on; one shared with others is still one. */
  dishes: number;
  /** The whole table shares it: no count is told. */
  everyone: boolean;
  share: number;
}

/** «×3» by the dish's name; nothing for a single dish or a shared one. */
const countLabel = ({ dishes, everyone }: PositionLine) => (everyone || dishes === 1 ? null : `×${dishes}`);

/** A participant's share of the receipt, one line per dish in receipt order.
 *  Several dishes of the same line collapse into one that counts them — «×2»
 *  of three beers — while the amount is what their share of those came to. */
export default function ParticipantPositions({ bill, participant }: {
  bill: BillDetail;
  participant: BillParticipant;
}) {
  const { t } = useTranslation();
  const currency = bill.currency ?? 'uzs';
  const lines = useMemo(() => {
    if (bill.split_type !== SplitType.BY_ITEMS) return [];
    const shares = tableSplit(bill.participants, bill.owner_id, bill.currency).splitItems(bill.items);
    return bill.items.flatMap((item): PositionLine[] => {
      const dishes = Array.from({ length: dishCount(item) }, (_, index) => dishEaters(item, index, bill.participants))
        .filter((eaters) => eaters.includes(participant.id)).length;
      if (dishes === 0) return [];
      const share = shares.get(item.id)?.get(participant.id) ?? 0;
      return [{ itemId: item.id, name: item.name, dishes, everyone: item.is_shared_globally, share }];
    });
  }, [bill, participant.id]);

  if (lines.length === 0) return null;

  return (
    <ul className="space-y-1.5" aria-label={t('bill.items')}>
      {lines.map((line) => {
        const count = countLabel(line);
        return (
          <li key={line.itemId} className="flex items-baseline gap-2 text-[13px] leading-snug">
            <span className="min-w-0 [overflow-wrap:anywhere]">
              {line.name}
              {count && <span className="ml-1 font-mono text-[11px] text-muted">{count}</span>}
            </span>
            <span aria-hidden="true" className="min-w-3 flex-1 translate-y-[-3px] border-b-[1.5px] border-dotted border-border" />
            <span className="flex-shrink-0 font-mono text-[12px] font-bold tabular-nums">
              {formatCurrency(line.share, currency)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
