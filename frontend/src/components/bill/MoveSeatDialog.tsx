'use client';

import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface MoveSeatDialogProps {
  isOpen: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/**
 * Asked before somebody changes seats.
 *
 * The seat being left keeps its dishes and the new one hands over its own, so a
 * move rewrites what the person owes. That is fine when they meant it and a
 * nasty surprise when they only tapped a link out of a chat — which is exactly
 * how it used to happen. The server refuses an unconfirmed move; this is the
 * question it is waiting for an answer to.
 */
export default function MoveSeatDialog({ isOpen, onCancel, onConfirm }: MoveSeatDialogProps) {
  const { t } = useTranslation();

  return (
    <Modal isOpen={isOpen} onClose={onCancel} title={t('bill.moveSeatTitle')} size="sm">
      <p className="text-[15px] leading-snug text-foreground">{t('bill.moveSeatConfirm')}</p>
      <div className="mt-5 flex gap-2.5">
        <Button variant="primary" className="flex-1" onClick={onCancel}>
          {t('common.back')}
        </Button>
        <Button variant="outline" className="flex-1" onClick={onConfirm}>
          {t('bill.moveSeatYes')}
        </Button>
      </div>
    </Modal>
  );
}
