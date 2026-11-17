'use client';

import Link from 'next/link';
import { SearchX, Home } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';

export default function NotFound() {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-6 text-center">
      <div className="mb-[18px] flex h-[58px] w-[58px] items-center justify-center rounded-[13px] border-[1.5px] border-outline text-muted-2">
        <SearchX className="h-[27px] w-[27px]" />
      </div>
      <h3 className="font-display text-[19px] font-bold text-foreground">
        {t('errors.pageNotFoundTitle')}
      </h3>
      <p className="mx-auto mt-2 max-w-[240px] text-[13px] font-medium leading-relaxed text-muted">
        {t('errors.pageNotFoundText')}
      </p>
      <Link
        href="/"
        className="mt-[22px] inline-flex items-center gap-2 rounded-lg border-[1.5px] border-outline bg-accent px-[22px] py-3 font-display text-[14px] font-bold text-accent-fg btn-hard"
      >
        <Home className="h-[17px] w-[17px]" />
        {t('errors.goHome')}
      </Link>
    </div>
  );
}
