'use client';

import PaymentDetailsChooser from '@/components/ui/PaymentDetailsChooser';
import type { PaymentChoice } from '@/hooks/usePaymentChoice';
import { useTranslation } from '@/lib/i18n/useTranslation';

/**
 * Step 2 — where everyone should transfer the money: one of the saved cards,
 * or another one typed in. Someone with no cards yet sees only the field and
 * a line on who will see it. The step's own Skip button says it can be left
 * empty.
 */
export default function StepPayment({ choice }: { choice: PaymentChoice }) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-2.5">
      <PaymentDetailsChooser choice={choice} label={t('bill.paymentAsk')} shortList />
      {choice.methods.length === 0 && (
        <p className="text-[12.5px] leading-snug text-muted">{t('bill.paymentHint')}</p>
      )}
    </div>
  );
}
