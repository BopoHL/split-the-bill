'use client';

import { Check, Lock } from 'lucide-react';
import Button from '@/components/ui/Button';
import { usePro } from '@/lib/store/usePro';
import { useTranslation } from '@/lib/i18n/useTranslation';

/**
 * What a part of analytics would show with Pro: a dimmed sketch of a chart,
 * what is in it, and the way to the paywall.
 */
export default function Locked({ title, items }: { title: string; items: string[] }) {
  const { t } = useTranslation();
  const openPaywall = usePro((state) => state.openPaywall);
  return (
    <section className="relative overflow-hidden rounded-lg border-[1.5px] border-outline bg-surface p-4">
      <div aria-hidden="true" className="pointer-events-none flex h-16 items-end gap-1.5 opacity-25 blur-[2px]">
        {[38, 64, 30, 92, 52, 76, 44].map((height, index) => (
          <span key={index} className={`flex-1 rounded-t-[3px] ${index === 3 ? 'bg-accent' : 'bg-foreground'}`} style={{ height: `${height}%` }} />
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border-[1.5px] border-outline bg-accent text-accent-fg">
          <Lock className="h-3.5 w-3.5" strokeWidth={2.5} />
        </span>
        <h3 className="font-display text-[16px] font-extrabold text-foreground">{title}</h3>
      </div>
      <ul className="mt-2.5 flex list-none flex-col gap-1.5 p-0">
        {items.map((item) => (
          <li key={item} className="flex items-start gap-2 text-[13px] text-foreground">
            <Check aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" strokeWidth={3} />
            {item}
          </li>
        ))}
      </ul>
      <Button className="mt-4 w-full" onClick={() => openPaywall('analytics')}>
        {t('pro.unlock')}
      </Button>
    </section>
  );
}
