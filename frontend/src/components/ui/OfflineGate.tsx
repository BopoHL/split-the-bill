'use client';

import { useEffect, useState } from 'react';
import { WifiOff, RefreshCw } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';

/**
 * Full-screen «no connection» state. Mounted once at the root; renders nothing
 * while online and an overlay (matching the Bold design) when the browser
 * reports it has gone offline.
 */
export default function OfflineGate() {
  const { t } = useTranslation();
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update();
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);

  if (!offline) return null;

  return (
    <div className="fixed inset-0 z-[70] flex flex-col items-center justify-center bg-background p-6 text-center">
      <div className="mb-[18px] flex h-[58px] w-[58px] items-center justify-center rounded-[13px] border-[1.5px] border-outline text-muted-2">
        <WifiOff className="h-[27px] w-[27px]" />
      </div>
      <h3 className="font-display text-[19px] font-bold text-foreground">
        {t('errors.offlineTitle')}
      </h3>
      <p className="mx-auto mt-2 max-w-[240px] text-[13px] font-medium leading-relaxed text-muted">
        {t('errors.offlineText')}
      </p>
      <button
        onClick={() => {
          if (navigator.onLine) setOffline(false);
          else window.location.reload();
        }}
        className="mt-[22px] inline-flex items-center gap-2 rounded-lg border-[1.5px] border-outline bg-surface px-[22px] py-3 font-display text-[14px] font-bold text-foreground btn-hard"
      >
        <RefreshCw className="h-[17px] w-[17px]" />
        {t('errors.retry')}
      </button>
    </div>
  );
}
