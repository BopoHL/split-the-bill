'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import { z } from 'zod';
import { billCreateSchema } from '@/lib/utils/validation';
import { displayToAmount } from '@/lib/utils/currency';

type BillCreateInput = z.input<typeof billCreateSchema>;

import { useTranslation } from '@/lib/i18n/useTranslation';

interface CreateBillModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: z.output<typeof billCreateSchema>) => void;
}

export default function CreateBillModal({ isOpen, onClose, onSubmit }: CreateBillModalProps) {
  const { t } = useTranslation();
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<BillCreateInput>({
    resolver: zodResolver(billCreateSchema),
  });

  const handleFinalSubmit = (data: BillCreateInput) => {
    onSubmit(data as z.output<typeof billCreateSchema>);
    reset();
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t('bill.createTitle')} size="sm">
      <form onSubmit={handleSubmit(handleFinalSubmit)} className="space-y-4">
        <Input
          label={t('bill.billTitle')}
          placeholder={t('bill.billTitle')}
          handwritten
          {...register('title')}
          error={errors.title?.message}
        />
        
        <Input
          label={t('bill.totalAmount')}
          type="text"
          inputMode="decimal"
          placeholder="0"
          {...register('total_sum', {
            setValueAs: (v) => displayToAmount(v),
          })}
          error={errors.total_sum?.message}
        />
        
        <Input
          label={t('bill.paymentDetails')}
          placeholder={t('bill.paymentDetails')}
          {...register('payment_details')}
          error={errors.payment_details?.message}
        />
        
        <label className="flex items-center gap-2 cursor-pointer pb-2">
          <input
            type="checkbox"
            {...register('include_creator')}
            className="w-5 h-5 rounded border-2 border-accent text-accent focus:ring-accent"
          />
          <span className="text-ink">{t('bill.includeMe')}</span>
        </label>
        
        <div className="flex justify-end gap-2 mt-4">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={isSubmitting}>
            {t('bill.createBill')}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
