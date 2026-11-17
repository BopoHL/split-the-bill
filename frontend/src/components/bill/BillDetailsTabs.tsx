'use client';

import type { ReactNode } from 'react';
import { ReceiptText, Users } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';
import SwipeTabs from '@/components/ui/SwipeTabs';
import { BACK_SWIPE_EDGE_PX } from '@/hooks/useEdgeSwipeBack';
import { TourAnchor } from '@/lib/tour/anchors';

export type BillTab = 'participants' | 'receipt';

export default function BillDetailsTabs({ value, onChange, participants, receipt }: {
  value: BillTab;
  onChange: (tab: BillTab) => void;
  participants: ReactNode;
  receipt: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <SwipeTabs
      label={t('bill.detailsTabs')}
      value={value}
      onChange={onChange}
      leftEdgeReserved={BACK_SWIPE_EDGE_PX}
      tourAnchor={TourAnchor.BillTabs}
      tabs={[
        { value: 'participants', label: t('bill.participants'), icon: Users, content: participants, tourAnchor: TourAnchor.ParticipantsTab },
        { value: 'receipt', label: t('bill.receipt'), icon: ReceiptText, content: receipt, tourAnchor: TourAnchor.ReceiptTab },
      ]}
    />
  );
}
