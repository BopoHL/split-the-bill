'use client';

import Button from '@/components/ui/Button';
import Modal from '@/components/ui/Modal';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface HomeScreenShortcutHelpProps {
  isOpen: boolean;
  isPending: boolean;
  platform: string | null;
  onClose: () => void;
  onRetry: () => void;
}

export default function HomeScreenShortcutHelp({
  isOpen,
  isPending,
  platform,
  onClose,
  onRetry,
}: HomeScreenShortcutHelpProps) {
  const { t } = useTranslation();
  const guidanceKey = platform === 'ios' ? 'iosHelp' : platform === 'android' ? 'androidHelp' : 'genericHelp';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t('homeScreen.helpTitle')}
      size="sm"
    >
      <div className="space-y-4">
        <p className="text-sm leading-relaxed text-foreground">
          {t('homeScreen.helpText')}
        </p>
        <p className="text-sm leading-relaxed text-muted">
          {t(`homeScreen.${guidanceKey}`)}
        </p>
        <p className="text-sm leading-relaxed text-muted">
          {t('homeScreen.telegramHelp')}
        </p>
        <div className="flex flex-col gap-2">
          <Button onClick={onRetry} isLoading={isPending}>
            {t('homeScreen.retry')}
          </Button>
          <Button variant="ghost" onClick={onClose} disabled={isPending}>
            {t('homeScreen.helpDone')}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
