'use client';

import { useState } from 'react';
import { BillDetail, User } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import Button from '@/components/ui/Button';
import { motion } from 'framer-motion';
import { updatePaymentStatus } from '@/lib/api/bills';
import BillOverview from './BillOverview';
import YouShareBlock from './YouShareBlock';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface BillDetailsParticipantProps {
  bill: BillDetail;
  currentUser: User | null;
  setBill: (bill: BillDetail) => void;
}

export default function BillDetailsParticipant({ bill, currentUser, setBill }: BillDetailsParticipantProps) {
  const { t } = useTranslation();
  // Find my participation record
  const myParticipation = bill.participants.find(p => p.user_id === currentUser?.id);
  const [loading, setLoading] = useState(false);

  const handleMarkPaid = async () => {
    if (!myParticipation || !currentUser) return;
    if (!confirm(t('bill.confirmPaymentAlert'))) return;

    try {
      setLoading(true);
      const updatedParticipant = await updatePaymentStatus(bill.id, myParticipation.id, true, currentUser.id);
      const updatedParticipants = bill.participants.map(p => 
        p.id === updatedParticipant.id ? updatedParticipant : p
      );
      setBill({ ...bill, participants: updatedParticipants });
    } catch (e) {
      console.error(e);
      alert(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  if (!myParticipation) {
    return (
      <div className="text-center py-10">
        <p className="text-ink/60 mb-4">{t('bill.notParticipant')}</p>
        <Button>{t('bill.joinBill')}</Button> 
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <BillOverview bill={bill} />

      <YouShareBlock 
        myParticipation={myParticipation} 
        onMarkPaid={handleMarkPaid} 
        loading={loading} 
      />

      {/* Participants Section */}
      <div>
        <div className="mb-3 px-1">
          <h2 className="text-lg font-handwritten text-ink">{t('bill.participants')} ({bill.participants.length})</h2>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {bill.participants.map((p) => {
            const isOwner = p.user_id === bill.owner_id;
            return (
              <motion.div
                key={p.id}
                layout
                className={`
                  p-3 rounded-lg border-2 
                  ${isOwner 
                    ? 'border-accent/40 bg-accent/5' 
                    : p.is_paid 
                      ? 'bg-green-50 border-green-200 dark:bg-green-900/10 dark:border-green-800' 
                      : 'bg-paper border-ink/10'
                  }
                `}
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="flex-1 min-w-0 pr-2">
                    <p className="font-medium text-ink truncate text-sm">
                      {p.guest_name || `User #${p.user_id}`}
                    </p>
                    <p className="text-xs text-ink/50">
                      {isOwner ? `👑 ${t('bill.creatorRole')}` : p.is_paid ? `${t('bill.paidLabel')} ✅` : `${t('bill.statusActive')} ⏳`}
                    </p>
                  </div>
                </div>
                
                <div className="relative h-8 flex items-center justify-end overflow-hidden">
                  <div className="font-bold text-ink">
                    {formatCurrency(p.allocated_amount)}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Items Section */}
      <div>
        <div className="mb-3 px-1">
          <h2 className="text-lg font-handwritten text-ink">{t('bill.items')} ({bill.items.length})</h2>
        </div>

        <div className="space-y-2">
          {bill.items.length === 0 ? (
            <div className="text-center py-6 border-2 border-dashed border-ink/10 rounded-lg">
              <p className="text-ink/40 text-sm">{t('bill.noItemsAdded')}</p>
            </div>
          ) : (
            <>
              <div className="flex items-center px-3 py-1 text-[10px] uppercase font-bold text-ink/40 border-b border-ink/5 mb-1">
                <div className="flex-[3] min-w-0">{t('bill.itemName')}</div>
                <div className="flex-1 text-center">{t('bill.quantity')}</div>
                <div className="flex-[2] text-right px-1">{t('bill.price')}</div>
                <div className="flex-[2] text-right">{t('common.total')}</div>
              </div>
              {bill.items.map((item) => (
                <div 
                  key={item.id}
                  className="flex items-center p-3 bg-paper rounded-lg border border-ink/10"
                >
                  <div className="flex-[3] min-w-0 pr-2">
                    <p className="text-ink text-sm font-medium truncate">{item.name}</p>
                  </div>
                  <div className="flex-1 text-center text-xs text-ink/60 font-mono">
                    {item.count}
                  </div>
                  <div className="flex-[2] text-right text-[11px] text-ink/40 font-mono px-1">
                    {formatCurrency(item.price)}
                  </div>
                  <div className="flex-[2] text-right">
                    <p className="font-mono text-sm font-bold text-accent leading-none">
                      {formatCurrency(item.item_sum)}
                    </p>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
