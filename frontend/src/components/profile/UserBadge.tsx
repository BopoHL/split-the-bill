'use client';

import type { CSSProperties } from 'react';
import { Beef, Coffee, MapPin, Moon, PartyPopper, Wallet, Zap, type LucideIcon } from 'lucide-react';
import ProBadge from '@/components/pro/ProBadge';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { PRO_BADGE } from '@/lib/utils/badges';

/** Each title's mark and colour — a colour of the theme's own palette, so it
 *  sits right in every theme. */
const LOOKS: Record<string, { icon: LucideIcon; hue: string }> = {
  coffee_lover: { icon: Coffee, hue: 'var(--chart-3)' },
  meat_lover: { icon: Beef, hue: 'var(--chart-1)' },
  regular: { icon: MapPin, hue: 'var(--chart-2)' },
  night_owl: { icon: Moon, hue: 'var(--chart-4)' },
  treasurer: { icon: Wallet, hue: 'var(--chart-5)' },
  social: { icon: PartyPopper, hue: 'var(--accent)' },
  fast_payer: { icon: Zap, hue: 'var(--star)' },
};
const NEUTRAL = 'var(--foreground)';

/** The badge by a name: Pro's stamp, or the title analytics gave them. */
export default function UserBadge({ badge, className = '' }: { badge: string | null | undefined; className?: string }) {
  const { t } = useTranslation();
  if (!badge) return null;
  if (badge === PRO_BADGE) return <ProBadge className={className} />;
  const title = t(`analytics.badge.${badge}.title`);
  const look = LOOKS[badge];
  const Icon = look?.icon;
  return (
    <span
      title={title}
      style={{ '--badge': look?.hue ?? NEUTRAL } as CSSProperties}
      className={`inline-flex h-[18px] min-w-0 max-w-[9rem] shrink items-center gap-[3px] rounded-[4px] border-[1.5px] border-[color-mix(in_oklab,var(--badge)_60%,var(--surface))] bg-[color-mix(in_oklab,var(--badge)_16%,var(--surface))] px-1 font-display text-[9px] font-extrabold uppercase leading-none tracking-[0.06em] text-[color-mix(in_oklab,var(--badge)_55%,var(--foreground))] ${className}`}
    >
      {Icon && <Icon aria-hidden="true" className="h-2.5 w-2.5 shrink-0" strokeWidth={2.75} />}
      <span className="truncate">{title}</span>
    </span>
  );
}
