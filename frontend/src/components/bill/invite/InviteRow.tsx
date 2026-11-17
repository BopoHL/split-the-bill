'use client';

import { Link2, Loader2, QrCode } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import Modal from '@/components/ui/Modal';
import type { BillDetail } from '@/types/api';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { TourAnchor } from '@/lib/tour/anchors';
import { useBillInvite } from './useBillInvite';

const HARD_ACTION =
  'btn-hard flex min-h-12 items-center justify-center rounded-lg border-[1.5px] border-outline font-display text-[14px] font-bold disabled:opacity-60';

/** Invite row heading the participants tab — available to everyone in the bill.
 *  Filling the table is what the tab is for until everyone is in, so the link
 *  is its one accent-coloured action.
 *
 *  A link icon, not a plus: this shares a link anyone at the table may take,
 *  and a plus read as «add another guest to the table», which is a different
 *  thing entirely and belongs to the owner alone. */
export default function InviteRow({ bill }: { bill: BillDetail }) {
  const { t } = useTranslation();
  const { sharing, share, qrOpen, qrLink, openQr, closeQr } = useBillInvite(bill);

  return (
    <>
      <div className="mb-5 flex items-stretch gap-2.5">
        <button
          type="button"
          onClick={share}
          disabled={sharing}
          data-tour={TourAnchor.Invite}
          className={`${HARD_ACTION} min-w-0 flex-1 gap-2 bg-accent px-3 py-2 text-accent-fg hover:bg-accent-hover`}
        >
          {sharing ? <Loader2 className="h-[18px] w-[18px] animate-spin" /> : <Link2 className="h-[18px] w-[18px]" />}
          {sharing ? t('bill.preparingShare') : t('bill.inviteParticipants')}
        </button>
        <button
          type="button"
          onClick={() => void openQr()}
          aria-label={t('bill.inviteQr')}
          title={t('bill.inviteQr')}
          className={`${HARD_ACTION} w-12 flex-shrink-0 bg-surface text-foreground hover:bg-accent-weak`}
        >
          <QrCode className="h-[18px] w-[18px]" />
        </button>
      </div>

      <Modal isOpen={qrOpen} onClose={closeQr} title={t('bill.inviteQrTitle')} size="sm">
        <div className="flex flex-col items-center gap-4 pb-2">
          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <QRCodeSVG value={qrLink} size={196} level="M" />
          </div>
          <p className="text-center text-sm text-muted">{t('bill.inviteQrHint')}</p>
        </div>
      </Modal>
    </>
  );
}
