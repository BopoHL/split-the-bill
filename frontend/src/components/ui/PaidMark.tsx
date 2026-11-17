import { DollarSign } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';

const SIZES = {
  sm: { box: 'h-6 w-6', icon: 'h-3.5 w-3.5' },
  md: { box: 'h-7 w-7', icon: 'h-[17px] w-[17px]' },
} as const;

interface PaidMarkProps {
  size?: keyof typeof SIZES;
}

/**
 * «Paid» in the «Bold» dress: a green square with a dollar sign, an ink
 * outline and the hard shadow. The picture of a shared bill draws the same
 * mark (backend `share_card._paid_mark`).
 */
export default function PaidMark({ size = 'md' }: PaidMarkProps) {
  const { t } = useTranslation();
  const label = t('bill.participantPaid');
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={`flex shrink-0 items-center justify-center rounded-[5px] border-[1.5px] border-outline bg-success text-success-fg shadow-[var(--shadow-hard-sm)] ${SIZES[size].box}`}
    >
      <DollarSign className={SIZES[size].icon} strokeWidth={2.5} />
    </span>
  );
}
