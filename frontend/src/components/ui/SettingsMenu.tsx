'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { GraduationCap, Headset, Settings, Smartphone } from 'lucide-react';
import { useStore } from '@/lib/store/useStore';
import { useTour } from '@/lib/tour/useTour';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { useHomeScreenShortcut } from '@/hooks/useHomeScreenShortcut';
import { useSupportUsername } from '@/hooks/useSupportUsername';
import { openTelegramLink } from '@/lib/telegram/init';
import { track, AnalyticsEvent } from '@/lib/analytics';
import Dropdown, { DropdownAction, DropdownDivider, DropdownLabel } from './Dropdown';

/** The app's settings: language, the home-screen shortcut, the tour and
 *  support. How the app looks is behind the profile in the header. */
export default function SettingsMenu() {
  const { language, setLanguage } = useStore();
  const { t } = useTranslation();
  const {
    showInSettings,
    isPending: isAddingToHomeScreen,
    add: addToHomeScreen,
  } = useHomeScreenShortcut();
  const [open, setOpen] = useState(false);
  const support = useSupportUsername();
  const router = useRouter();
  const pathname = usePathname();
  const startTour = useTour((state) => state.start);

  // The tour begins on the home screen, whichever screen asked for it.
  const replayTour = () => {
    setOpen(false);
    startTour('settings');
    if (pathname !== '/') router.push('/');
  };

  return (
    <Dropdown
      open={open}
      onClose={() => setOpen(false)}
      label={t('settings.title')}
      trigger={
        <button
          onClick={() => setOpen((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={t('settings.title')}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-bar-fg opacity-80 transition hover:bg-white/10 hover:opacity-100"
        >
          <Settings className="h-5 w-5" />
        </button>
      }
    >
      {showInSettings && (
        <>
          <DropdownAction
            icon={Smartphone}
            label={isAddingToHomeScreen ? t('homeScreen.checking') : t('homeScreen.settingsItem')}
            disabled={isAddingToHomeScreen}
            onClick={() => {
              addToHomeScreen();
              setOpen(false);
            }}
          />
          <DropdownDivider />
        </>
      )}

      <DropdownLabel>{t('settings.language')}</DropdownLabel>
      <div className="flex gap-1 px-3.5 pb-2">
        {(['en', 'ru', 'uz'] as const).map((lng) => (
          <button
            key={lng}
            onClick={() => {
              setLanguage(lng);
              setOpen(false);
            }}
            className={`flex-1 rounded-md border-[1.5px] py-1.5 text-center font-display text-[11px] font-bold uppercase transition-colors ${
              language === lng
                ? 'border-accent bg-accent text-accent-fg'
                : 'border-border text-muted hover:border-outline'
            }`}
          >
            {lng}
          </button>
        ))}
      </div>

      <DropdownDivider />

      <DropdownAction icon={GraduationCap} label={t('settings.tutorial')} onClick={replayTour} />

      {/* Offered once the app knows whom it goes to. */}
      {support && (
        <DropdownAction
          icon={Headset}
          label={t('settings.support')}
          onClick={() => {
            openTelegramLink(`https://t.me/${support}`);
            track(AnalyticsEvent.SupportOpened, {});
            setOpen(false);
          }}
        />
      )}
    </Dropdown>
  );
}
