'use client';

import { useEffect, useState } from 'react';
import { Link2 } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import type { BillDetail } from '@/types/api';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { useInvitePrompt } from '@/lib/store/useInvitePrompt';
import { useBillInvite } from './useBillInvite';

/** Right after a bill is made: send it to the table now, while everyone is
 *  still there — the same invite the participants tab offers. */
export default function InvitePrompt({ bill }: { bill: BillDetail }) {
  const { t } = useTranslation();
  const { sharing, share } = useBillInvite(bill);
  const [open, setOpen] = useState(() => useInvitePrompt.getState().billId === bill.id);

  useEffect(() => {
    if (useInvitePrompt.getState().claim(bill.id)) {
      track(AnalyticsEvent.InvitePromptShown, { bill_id: bill.id });
    }
  }, [bill.id]);

  const send = async () => {
    await share();
    setOpen(false);
  };

  const later = () => {
    setOpen(false);
    track(AnalyticsEvent.InvitePromptDismissed, { bill_id: bill.id });
  };

  return (
    <Modal isOpen={open} onClose={later} title={t('bill.invitePromptTitle')} size="sm">
      <div className="space-y-4">
        <p className="text-sm text-muted">{t('bill.invitePromptText')}</p>
        <div className="flex flex-col gap-2">
          <Button onClick={() => void send()} isLoading={sharing}>
            <Link2 className="h-[18px] w-[18px]" />
            {t('bill.inviteParticipants')}
          </Button>
          <Button variant="ghost" onClick={later} disabled={sharing}>
            {t('bill.invitePromptLater')}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
