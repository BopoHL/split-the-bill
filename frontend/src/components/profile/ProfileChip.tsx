'use client';

import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { useStore } from '@/lib/store/useStore';
import { useIsPro, useProGate } from '@/lib/store/usePro';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { shownTheme } from '@/lib/utils/themes';
import { shownBadge } from '@/lib/utils/badges';
import Dropdown, { DropdownLabel, DropdownRow } from '@/components/ui/Dropdown';
import ThemePicker from '@/components/ui/ThemePicker';
import ThemeDot from '@/components/ui/ThemeDot';
import BadgePicker from './BadgePicker';
import UserBadge from './UserBadge';

/**
 * Who is signed in — their picture — beside the theme they use, which says
 * this is where the app's look is changed: its theme and the badge by the name.
 */
export default function ProfileChip({ className = '' }: { className?: string }) {
  const { t } = useTranslation();
  const { theme, currentUser } = useStore();
  const isPro = useIsPro();
  const { locked: themesLocked } = useProGate('themes');
  const [open, setOpen] = useState(false);
  const [picking, setPicking] = useState<'theme' | 'badge' | null>(null);
  if (!currentUser) return null;

  const badge = shownBadge(currentUser.settings?.badge, isPro);
  const shown = shownTheme(theme, themesLocked);
  const pick = (what: 'theme' | 'badge') => {
    setOpen(false);
    setPicking(what);
  };

  return (
    <>
      <Dropdown
        open={open}
        onClose={() => setOpen(false)}
        label={t('settings.appearance')}
        className={`min-w-0 ${className}`}
        trigger={
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={open}
            aria-label={t('settings.appearance')}
            className="flex h-9 shrink-0 items-center gap-2 rounded-md border border-white/20 pl-1 pr-2 transition hover:bg-white/10"
          >
            {currentUser.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={currentUser.avatar_url}
                alt=""
                className="h-6 w-6 shrink-0 rounded object-cover outline outline-1 -outline-offset-1 outline-white/10"
              />
            ) : (
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-accent font-display text-[11px] font-bold text-accent-fg">
                {(currentUser.username || 'U').charAt(0).toUpperCase()}
              </span>
            )}
            <ThemeDot theme={shown} className="h-[18px] w-[18px] border-white/50" />
          </button>
        }
      >
        <DropdownLabel>{t('settings.theme')}</DropdownLabel>
        <DropdownRow onClick={() => pick('theme')}>
          <ThemeDot theme={shown} />
          <span className="min-w-0 flex-1">{t(`settings.themes.${shown}`)}</span>
          <ChevronRight className="h-4 w-4 shrink-0 text-muted" />
        </DropdownRow>

        <DropdownLabel>{t('settings.badge')}</DropdownLabel>
        <DropdownRow onClick={() => pick('badge')}>
          <span className="flex min-w-0 flex-1">{badge ? <UserBadge badge={badge} /> : t('settings.badgeNone')}</span>
          <ChevronRight className="h-4 w-4 shrink-0 text-muted" />
        </DropdownRow>
      </Dropdown>
      <ThemePicker isOpen={picking === 'theme'} onClose={() => setPicking(null)} />
      <BadgePicker isOpen={picking === 'badge'} onClose={() => setPicking(null)} />
    </>
  );
}
