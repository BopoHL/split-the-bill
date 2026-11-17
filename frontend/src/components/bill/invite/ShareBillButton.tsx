'use client';

import { Loader2, Share } from 'lucide-react';
import type { BillDetail } from '@/types/api';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { useBillInvite } from './useBillInvite';

/** Header share action — the same invite the participant list offers. The
 *  bill's one call to action up there, so it is the accent key, not an icon. */
export default function ShareBillButton({ bill }: { bill: BillDetail }) {
  const { t } = useTranslation();
  const { sharing, share } = useBillInvite(bill);

  return (
    <button
      onClick={() => void share()}
      disabled={sharing}
      aria-label={t('common.invite')}
      className="btn-hard-sm ml-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border-[1.5px] border-outline bg-accent text-accent-fg hover:bg-accent-hover disabled:opacity-50"
    >
      {sharing ? <Loader2 className="h-[18px] w-[18px] animate-spin" /> : <Share className="h-[18px] w-[18px]" strokeWidth={2.25} />}
    </button>
  );
}
