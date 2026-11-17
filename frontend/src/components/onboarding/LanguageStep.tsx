'use client';

import { ArrowRight, Check } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { useStore } from '@/lib/store/useStore';

interface LanguageStepProps {
  /** On to the guided tour, in the language just picked. */
  onContinue: () => void;
}

const LANGUAGES = [
  { code: 'ru', label: 'Русский', flag: '🇷🇺' },
  { code: 'uz', label: "O'zbekcha", flag: '🇺🇿' },
  { code: 'en', label: 'English', flag: '🇬🇧' },
] as const;

// A full-screen layer of its own, so it sits outside AppHeader — the one
// element that otherwise applies Telegram's insets. In fullscreen the client's
// close and menu buttons float over the top of the page, which is what
// `--content-safe-top` measures, and the home indicator is what the bottom one
// does.
const SHEET = 'fixed inset-0 z-[60] flex flex-col overflow-y-auto overscroll-contain bg-surface pl-[var(--content-safe-left)] pr-[var(--content-safe-right)]';

/** The one screen before the app: everything after it, the tour included,
 *  speaks the language chosen here. */
export default function LanguageStep({ onContinue }: LanguageStepProps) {
  const { t, language } = useTranslation();
  const { setLanguage } = useStore();

  return (
    <div className={SHEET}>
      <div className="px-6 pb-3 pt-[calc(3rem+var(--content-safe-top))] text-center">
        <h2 className="font-display text-[22px] font-bold tracking-[-0.01em] text-foreground">
          {t('onboarding.languageTitle')}
        </h2>
        <p className="mx-auto mt-2 max-w-[280px] text-[13px] font-medium leading-relaxed text-muted">
          {t('onboarding.languageText')}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto px-6 pb-3">
        <div className="mx-auto flex w-full max-w-[320px] flex-col gap-2.5">
          {LANGUAGES.map((l) => {
            const active = l.code === language;
            return (
              <button
                key={l.code}
                onClick={() => setLanguage(l.code)}
                aria-pressed={active}
                className={`flex items-center gap-3 rounded-[12px] border-[1.5px] px-4 py-3 transition-colors ${
                  active ? 'border-accent bg-accent-weak' : 'border-border hover:border-outline'
                }`}
              >
                <span className="text-[24px] leading-none">{l.flag}</span>
                <span className={`font-display text-[15px] font-bold ${active ? 'text-accent' : 'text-foreground'}`}>
                  {l.label}
                </span>
                {active && <Check className="ml-auto h-4 w-4 text-accent" />}
              </button>
            );
          })}
        </div>
      </div>
      <div className="px-6 pb-[calc(2.25rem+var(--content-safe-bottom))] pt-3 text-center">
        <button
          onClick={onContinue}
          className="inline-flex items-center gap-2.5 rounded-[7px] border-[1.5px] border-outline bg-accent px-[22px] py-[13px] font-display text-[14px] font-bold text-accent-fg btn-hard"
        >
          <ArrowRight className="h-4 w-4" />
          {t('onboarding.next')}
        </button>
      </div>
    </div>
  );
}
