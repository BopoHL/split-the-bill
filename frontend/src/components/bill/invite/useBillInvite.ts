'use client';

import { useCallback, useState } from 'react';
import type { BillDetail } from '@/types/api';
import { inviteDeepLink, prepareShareMessage } from '@/lib/api/bills';
import { createInvite } from '@/lib/api/invites';
import { canShareMessage, shareMessage } from '@/lib/telegram/share';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { showToast } from '@/lib/toast';
import { translateApiError } from '@/lib/utils/apiError';

/**
 * Inviting someone to a bill.
 *
 * One implementation for every entry point — the header's share button and the
 * row under the participant list used to be two different things, and only the
 * owner had the good one. Anyone in the bill can invite: whoever is at the table
 * is as likely to be the one messaging the group.
 */
export function useBillInvite(bill: BillDetail) {
  const { t, language } = useTranslation();
  const [sharing, setSharing] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const [qrLink, setQrLink] = useState<string | null>(null);

  const tokenLink = inviteDeepLink(bill.public_token);

  /** A link that remembers who shared it; the token link if minting fails. */
  const mintQrLink = async () => {
    try {
      return (await createInvite(bill.id, 'qr')).deep_link;
    } catch {
      return tokenLink;
    }
  };

  const openQr = useCallback(async () => {
    setQrOpen(true);
    track(AnalyticsEvent.ShareInvite, { method: 'qr', channel: 'qr', bill_id: bill.id });
    setQrLink(await mintQrLink());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bill.id]);

  /** The bill's chat post, written and kept current by the server, handed to
   *  Telegram's share sheet. It is the only invite there is: when the sheet
   *  can't be shown, the person is told why rather than handed a lesser one. */
  const share = async () => {
    if (sharing) return;
    if (!canShareMessage()) {
      showToast(t('bill.shareUnsupported'));
      return;
    }

    try {
      setSharing(true);
      const preparedId = await prepareShareMessage(bill.id, language);
      if (shareMessage(preparedId)) track(AnalyticsEvent.ShareInvite, { method: 'message', channel: 'prepared', bill_id: bill.id });
      else showToast(t('bill.shareUnsupported'));
    } catch (e: unknown) {
      console.error(e);
      showToast(
        translateApiError(
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail,
          t,
        ),
      );
    } finally {
      setSharing(false);
    }
  };

  return {
    sharing,
    share,
    qrOpen,
    qrLink: qrLink ?? tokenLink,
    openQr,
    closeQr: () => setQrOpen(false),
  };
}
