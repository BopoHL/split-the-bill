'use client';

import { useState } from 'react';
import { BillDetail, SplitType, User } from '@/types/api';
import { formatCurrency, displayToAmount } from '@/lib/utils/currency';
import Button from '@/components/ui/Button';
import { Plus, Users, Trash2 } from 'lucide-react';
import { motion } from 'framer-motion';
import Modal from '@/components/ui/Modal';
import Input from '@/components/ui/Input';
import { addBillParticipant, addBillItem, deleteBillItem, assignAmount, updatePaymentStatus, deleteBillParticipant, splitRemainder, generateTelegramShareLink } from '@/lib/api/bills';
import { shareLink } from '@/lib/telegram/init';
import BillOverview from './BillOverview';
import YouShareBlock from './YouShareBlock';
import ParticipantCard from './ParticipantCard';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface BillDetailsCreatorProps {
  bill: BillDetail;
  setBill: (bill: BillDetail) => void;
  currentUser: User | null;
  reactions?: Record<number, string>;
}

export default function BillDetailsCreator({ bill, setBill, currentUser, reactions = {} }: BillDetailsCreatorProps) {
  const { t } = useTranslation();
  const [showAddParticipant, setShowAddParticipant] = useState(false);
  const [showAddItem, setShowAddItem] = useState(false);
  const [newParticipantName, setNewParticipantName] = useState('');
  const [newItemName, setNewItemName] = useState('');
  const [newItemPrice, setNewItemPrice] = useState('');
  const [newItemCount, setNewItemCount] = useState('1');
  const [loading, setLoading] = useState(false);

  const handleSplitBetween = async (participantIds: number[]) => {
    if (participantIds.length === 0) {
      alert(t('bill.selectParticipantsAlert'));
      return;
    }
    
    try {
      setLoading(true);
      const updatedParticipants = await splitRemainder(bill.id, participantIds);
      setBill({
        ...bill,
        participants: updatedParticipants,
        split_type: SplitType.MANUAL,
        unallocated_sum: 0
      });
    } catch (e) {
      console.error(e);
      alert(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const handleAddParticipant = async () => {
    if (!newParticipantName.trim()) return;
    try {
      setLoading(true);
      const updatedParticipants = await addBillParticipant(bill.id, {
        guest_name: newParticipantName,
      });
      
      setBill({
        ...bill,
        participants: updatedParticipants,
      });
      setNewParticipantName('');
      setShowAddParticipant(false);
    } catch (e) {
      console.error(e);
      alert(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const handleItemPriceChange = (val: string) => {
    if (val === '' || /^\d*[.,]?\d{0,2}$/.test(val)) {
      setNewItemPrice(val);
    }
  };

  const handleAddItem = async () => {
    if (!newItemName.trim() || !newItemPrice) return;
    try {
      setLoading(true);
      const newItem = await addBillItem(bill.id, {
        name: newItemName,
        price: displayToAmount(newItemPrice),
        count: parseInt(newItemCount) || 1,
      });
      
      setBill({
        ...bill,
        items: [...bill.items, newItem],
        split_type: SplitType.MANUAL
      });
      setNewItemName('');
      setNewItemPrice('');
      setNewItemCount('1');
      setShowAddItem(false);
    } catch (e) {
      console.error(e);
      alert(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteItem = async (itemId: number) => {
    try {
      setLoading(true);
      await deleteBillItem(bill.id, itemId);
      setBill({
        ...bill,
        items: bill.items.filter(item => item.id !== itemId)
      });
    } catch (e) {
      console.error(e);
      alert(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const myParticipation = bill.participants.find(p => p.user_id === currentUser?.id);

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

  const handleTogglePaymentStatus = async (participantId: number, currentPaid: boolean) => {
    if (!currentUser) return;
    
    const actionText = currentPaid ? t('bill.cancelPaymentAlert') : t('bill.confirmPaymentAlert');
    if (!confirm(actionText)) return;

    try {
      setLoading(true);
      const updatedParticipant = await updatePaymentStatus(bill.id, participantId, !currentPaid, currentUser.id);
      
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

  const handleDeleteParticipant = async (participantId: number) => {
    if (!currentUser) return;
    if (!confirm(t('bill.removeParticipantAlert'))) return;
    
    try {
      setLoading(true);
      const updatedBill = await deleteBillParticipant(bill.id, participantId, currentUser.id);
      setBill(updatedBill);
    } catch (e) {
      console.error(e);
      alert(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const handleAssignAmount = async (participantId: number, amount: number) => {
    try {
      setLoading(true);
      const updatedParticipant = await assignAmount(bill.id, participantId, amount);
      
      const newParticipants = bill.participants.map(p => 
        p.id === participantId ? updatedParticipant : p
      );
      
      const oldParticipant = bill.participants.find(p => p.id === participantId);
      const diff = updatedParticipant.allocated_amount - (oldParticipant?.allocated_amount || 0);
      
      setBill({
        ...bill,
        participants: newParticipants,
        unallocated_sum: Math.max(0, bill.unallocated_sum - diff),
        split_type: SplitType.MANUAL
      });
    } catch (e) {
      console.error(e);
      alert(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <BillOverview 
        bill={bill} 
        onSplitBetween={handleSplitBetween} 
        loading={loading} 
      />

      {myParticipation && (
        <YouShareBlock 
          billId={bill.id}
          myParticipation={myParticipation} 
          onMarkPaid={handleMarkPaid} 
          loading={loading} 
          hideAction={true}
        />
      )}

      {/* Participants Section */}
      <div>
        <div className="flex items-center justify-between mb-3 px-1">
          <h2 className="text-lg font-handwritten text-ink">{t('bill.participants')} ({bill.participants.length})</h2>
          {!bill.is_closed && (
            <div className="flex items-center gap-2">
              <Button 
                size="sm" 
                variant="outline" 
                className="text-accent border-accent/20 hover:bg-accent/5"
                onClick={() => {
                  const link = generateTelegramShareLink(bill.id, bill.title || '');
                  shareLink(link);
                }}
              >
                <Users className="w-4 h-4 mr-1" /> {t('common.invite')}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowAddParticipant(true)}>
                <Plus className="w-4 h-4 mr-1" /> {t('common.add')}
              </Button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          {bill.participants.map((p) => (
            <ParticipantCard 
              key={p.id}
              participant={p}
              isOwner={p.user_id === bill.owner_id}
              reaction={p.user_id ? reactions[p.user_id] : undefined}
              isCreatorView={true}
              onDelete={handleDeleteParticipant}
              onTogglePayment={handleTogglePaymentStatus}
              onAssignAmount={handleAssignAmount}
            />
          ))}
          
          {!bill.is_closed && (
            <motion.div
              layout
              onClick={() => setShowAddParticipant(true)}
              className="p-3 rounded-lg border-2 border-dashed border-ink/20 flex flex-col items-center justify-center min-h-[90px] cursor-pointer hover:bg-black/5 transition-colors"
            >
              <div className="w-8 h-8 rounded-full bg-ink/5 flex items-center justify-center mb-1">
                <Plus className="w-4 h-4 text-ink/40" />
              </div>
              <span className="text-xs text-ink/40 font-medium">{t('bill.addParticipant')}</span>
            </motion.div>
          )}
        </div>
      </div>

      {/* Items Section */}
      <div>
        <div className="flex items-center justify-between mb-3 px-1">
          <h2 className="text-lg font-handwritten text-ink">{t('bill.items')} ({bill.items.length})</h2>
          {!bill.is_closed && (
            <Button size="sm" variant="ghost" onClick={() => setShowAddItem(true)}>
              <Plus className="w-4 h-4 mr-1" /> {t('common.add')}
            </Button>
          )}
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
                <div className="w-8"></div>
              </div>
              {bill.items.map((item) => (
                <div 
                  key={item.id}
                  className="flex items-center p-3 bg-paper rounded-lg border border-ink/10 hover:border-accent/10 transition-colors"
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
                  <div className="w-8 flex justify-end">
                    <button 
                      onClick={() => handleDeleteItem(item.id)}
                      className="p-1.5 text-ink/20 hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      {/* Modals */}
      <Modal 
        isOpen={showAddParticipant} 
        onClose={() => setShowAddParticipant(false)}
        title={t('bill.addParticipant')}
        size="sm"
      >
        <div className="space-y-4">
          <Input 
            label={t('bill.guestName')} 
            placeholder={t('bill.guestName')} 
            value={newParticipantName}
            onChange={(e) => setNewParticipantName(e.target.value)}
          />
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={() => setShowAddParticipant(false)}>{t('common.cancel')}</Button>
            <Button onClick={handleAddParticipant} disabled={loading}>{t('common.add')}</Button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={showAddItem}
        onClose={() => setShowAddItem(false)}
        title={t('bill.addItem')}
        size="sm"
      >
        <div className="space-y-4">
          <Input 
            label={t('bill.itemName')} 
            placeholder={t('bill.itemName')}
            value={newItemName}
            onChange={(e) => setNewItemName(e.target.value)}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input 
              label={t('bill.price')} 
              type="text"
              inputMode="decimal"
              placeholder="0"
              value={newItemPrice}
              onChange={(e) => handleItemPriceChange(e.target.value)}
            />
            <Input 
              label={t('bill.quantity')} 
              type="number"
              min="1"
              value={newItemCount}
              onChange={(e) => setNewItemCount(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={() => setShowAddItem(false)}>{t('common.cancel')}</Button>
            <Button onClick={handleAddItem} disabled={loading}>{t('bill.addItem')}</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
