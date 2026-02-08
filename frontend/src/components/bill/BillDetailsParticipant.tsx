import { useState } from 'react';
import { BillDetail, User } from '@/types/api';
import YouShareBlock from './YouShareBlock';
import BillOverview from './BillOverview';
import ParticipantCard from './ParticipantCard';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { updatePaymentStatus } from '@/lib/api/bills';
import Button from '@/components/ui/Button';

interface BillDetailsParticipantProps {
  bill: BillDetail;
  currentUser: User | null;
  setBill: (bill: BillDetail) => void;
  reactions?: Record<number, string>;
}

export default function BillDetailsParticipant({ bill, currentUser, setBill, reactions = {} }: BillDetailsParticipantProps) {
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
    } catch (e: unknown) {
      console.error(e);
      const message = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('common.error');
      alert(message);
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
        billId={bill.id}
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
          {bill.participants.map((p) => (
            <ParticipantCard 
              key={p.id}
              participant={p}
              isOwner={p.user_id === bill.owner_id}
              reaction={p.user_id ? reactions[p.user_id] : undefined}
            />
          ))}
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
