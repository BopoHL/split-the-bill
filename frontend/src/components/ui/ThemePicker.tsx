'use client';

import { useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Check } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import ProBadge from '@/components/pro/ProBadge';
import { useStore } from '@/lib/store/useStore';
import { usePro, useProGate } from '@/lib/store/usePro';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { isProTheme, shownTheme, THEMES, type Theme } from '@/lib/utils/themes';
import ThemePreview, { type PreviewView } from './ThemePreview';
import ThemeDot from './ThemeDot';

const VIEWS: PreviewView[] = ['bill', 'chat'];

/**
 * Themes tried on before they are taken: a tap shows a bill's screen, or its
 * post in a chat, in that theme; the button below takes it — or, for a Pro
 * theme without Pro, opens the paywall.
 */
export default function ThemePicker({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const { theme, selectTheme } = useStore();
  const { locked } = useProGate('themes');
  const openPaywall = usePro((state) => state.openPaywall);
  const reduceMotion = useReducedMotion();
  const shown = shownTheme(theme, locked);
  const [tried, setTried] = useState<Theme | null>(null);
  const [view, setView] = useState<PreviewView>('bill');
  const candidate = tried ?? shown;
  const candidateLocked = isProTheme(candidate) && locked;

  const close = () => {
    setTried(null);
    onClose();
  };
  const take = () => {
    if (candidateLocked) {
      openPaywall('themes', () => selectTheme(candidate));
      return;
    }
    selectTheme(candidate);
    close();
  };

  return (
    <Modal isOpen={isOpen} onClose={close} title={t('settings.theme')} size="md">
      <div className="flex min-h-0 flex-col gap-3 p-4">
        <div className="flex min-h-0 flex-col gap-3 overflow-y-auto overscroll-contain">
          <div role="tablist" aria-label={t('settings.theme')} className="grid grid-cols-2 rounded-lg border-[1.5px] border-outline bg-surface p-[3px] font-display text-[12px] font-bold">
            {VIEWS.map((option) => (
              <button
                key={option}
                type="button"
                role="tab"
                aria-selected={view === option}
                onClick={() => setView(option)}
                className={`min-h-9 rounded-[5px] transition-colors ${view === option ? 'bg-emphasis text-emphasis-fg' : 'text-muted'}`}
              >
                {t(`settings.preview.${option}Tab`)}
              </button>
            ))}
          </div>

          <div className="relative" data-testid="theme-preview" data-previewed={candidate}>
            <AnimatePresence mode="popLayout" initial={false}>
              <motion.div
                key={`${candidate}-${view}`}
                initial={reduceMotion ? false : { opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                transition={{ type: 'spring', duration: 0.3, bounce: 0 }}
              >
                <ThemePreview theme={candidate} view={view} />
              </motion.div>
            </AnimatePresence>
          </div>

          <div role="radiogroup" aria-label={t('settings.theme')} className="flex flex-wrap gap-2">
            {THEMES.map(({ id, pro }) => {
              const tryingIt = candidate === id;
              return (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={tryingIt}
                  onClick={() => setTried(id)}
                  className={`flex min-h-11 items-center gap-1.5 rounded-full border-[1.5px] pl-2 pr-3 font-display text-[13px] font-bold transition-colors ${
                    tryingIt ? 'border-accent bg-accent-weak text-foreground' : 'border-border text-foreground hover:border-outline'
                  }`}
                >
                  <ThemeDot theme={id} />
                  <span>{t(`settings.themes.${id}`)}</span>
                  {pro && locked && <ProBadge />}
                  {shown === id && <Check aria-label={t('settings.preview.chosen')} className="h-4 w-4 text-accent" strokeWidth={3} />}
                </button>
              );
            })}
          </div>

          {locked && <p className="text-[12px] leading-snug text-muted">{t('settings.themesHint')}</p>}
        </div>

        <Button className="w-full" onClick={take} disabled={candidate === shown}>
          {candidate === shown ? t('settings.preview.chosen') : candidateLocked ? t('pro.unlock') : t('settings.preview.choose')}
        </Button>
      </div>
    </Modal>
  );
}
