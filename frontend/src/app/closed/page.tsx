'use client';

import { useRouter } from 'next/navigation';
import { Home, Check } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';

// Shown when a non-participant opens an invite link to a closed bill: joining
// isn't possible, so we explain it plainly and offer a way home (STB-230).
export default function ClosedBillPage() {
  const router = useRouter();
  const { t } = useTranslation();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-6 text-center">
      <div className="mb-[18px] flex h-[58px] w-[58px] items-center justify-center rounded-[13px] border-[1.5px] border-outline text-muted-2">
        <Check className="h-[27px] w-[27px]" />
      </div>
      <h3 className="font-display text-[19px] font-bold text-foreground">
        {t('errors.closedBillTitle')}
      </h3>
      <p className="mx-auto mt-2 max-w-[240px] text-[13px] font-medium leading-relaxed text-muted">
        {t('errors.closedBillText')}
      </p>
      <button
        onClick={() => router.push('/')}
        className="mt-[22px] inline-flex items-center gap-2 rounded-lg border-[1.5px] border-outline bg-accent px-[22px] py-3 font-display text-[14px] font-bold text-accent-fg btn-hard"
      >
        <Home className="h-[17px] w-[17px]" />
        {t('errors.goHome')}
      </button>
    </div>
  );
}
