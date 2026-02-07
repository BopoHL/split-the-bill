'use client';

import { useState } from 'react';
import { BillDetail, SplitType, User } from '@/types/api';
import { formatCurrency, displayToAmount } from '@/lib/utils/currency';
import Button from '@/components/ui/Button';
import { Plus, Check, X, Trash2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import Modal from '@/components/ui/Modal';
import Input from '@/components/ui/Input';
import { addBillParticipant, addBillItem, deleteBillItem, assignAmount, updatePaymentStatus, deleteBillParticipant, splitRemainder } from '@/lib/api/bills';
import BillOverview from './BillOverview';
import YouShareBlock from './YouShareBlock';

interface BillDetailsCreatorProps {
  bill: BillDetail;
  setBill: (bill: BillDetail) => void;
  currentUser: User | null;
}

export default function BillDetailsCreator({ bill, setBill, currentUser }: BillDetailsCreatorProps) {
  const [showAddParticipant, setShowAddParticipant] = useState(false);
  const [showAddItem, setShowAddItem] = useState(false);
  const [newParticipantName, setNewParticipantName] = useState('');
  const [newItemName, setNewItemName] = useState('');
  const [newItemPrice, setNewItemPrice] = useState('');
  const [newItemCount, setNewItemCount] = useState('1');
  const [loading, setLoading] = useState(false);
  const [assigningId, setAssigningId] = useState<number | null>(null);
  const [assignmentValue, setAssignmentValue] = useState('');

  const handleSplitBetween = async (participantIds: number[]) => {
    if (participantIds.length === 0) {
      alert('Select participants first!');
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
      alert('Failed to split');
    } finally {
      setLoading(false);
    }
  };

  const handleAssignAmount = async (participantId: number) => {
    const amount = displayToAmount(assignmentValue);
    if (isNaN(amount) || amount < 0) return;

    try {
      setLoading(true);
      const updatedParticipant = await assignAmount(bill.id, participantId, amount);
      
      // Update local state
      const newParticipants = bill.participants.map(p => 
        p.id === participantId ? updatedParticipant : p
      );
      
      // Calculate new unallocated amount (backend recalculates, but we can be optimistic)
      // Actually, since we have the updated participant from backend, we just need the new total unallocated
      // But the assignAmount returns just the participant. 
      // Let's assume the user just wants the participant updated, and they will refresh or we can recalculate.
      // Wait, the Bill interface has unallocated_amount. I should probably refetch or recalculate.
      // For now, let's recalculate unallocated_amount based on the change.
      const oldParticipant = bill.participants.find(p => p.id === participantId);
      const diff = updatedParticipant.allocated_amount - (oldParticipant?.allocated_amount || 0);
      
      setBill({
        ...bill,
        participants: newParticipants,
        unallocated_sum: Math.max(0, bill.unallocated_sum - diff),
        split_type: SplitType.MANUAL
      });
      
      setAssigningId(null);
      setAssignmentValue('');
    } catch (e) {
      console.error(e);
      alert('Failed to assign amount');
    } finally {
      setLoading(false);
    }
  };

  const handleAssignmentInputChange = (val: string) => {
    // Check if it's a valid number first or empty (allow dot and comma, max 2 decimals)
    if (val === '' || /^\d*[.,]?\d{0,2}$/.test(val)) {
      const amount = displayToAmount(val);
      // Cap at unallocated_amount + current allocated
      const participant = bill.participants.find(p => p.id === assigningId);
      const currentAllocated = participant?.allocated_amount || 0;
      const maxPossible = bill.unallocated_sum + currentAllocated;

      if (amount > maxPossible) {
        setAssignmentValue(maxPossible.toString());
      } else {
        setAssignmentValue(val);
      }
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
      alert('Failed to add participant');
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
      alert('Failed to add item');
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
      alert('Failed to delete item');
    } finally {
      setLoading(false);
    }
  };

  // Find my participation record
  const myParticipation = bill.participants.find(p => p.user_id === currentUser?.id);

  const handleMarkPaid = async () => {
    if (!myParticipation || !currentUser) return;
    if (!confirm('Are you sure you have transferred the money? This cannot be undone.')) return;

    try {
      setLoading(true);
      const updatedParticipant = await updatePaymentStatus(bill.id, myParticipation.id, true, currentUser.id);
      // Update local state with real value from backend
      const updatedParticipants = bill.participants.map(p => 
        p.id === updatedParticipant.id ? updatedParticipant : p
      );
      setBill({ ...bill, participants: updatedParticipants });
    } catch (e) {
      console.error(e);
      alert('Failed to update status');
    } finally {
      setLoading(false);
    }
  };

  const handleTogglePaymentStatus = async (participantId: number, currentPaid: boolean) => {
    if (!currentUser) return;
    
    const actionText = currentPaid ? 'Cancel payment confirmation?' : 'Confirm payment?';
    if (!confirm(actionText)) return;

    try {
      setLoading(true);
      const updatedParticipant = await updatePaymentStatus(bill.id, participantId, !currentPaid, currentUser.id);
      
      // Update local state with real value from backend
      const updatedParticipants = bill.participants.map(p => 
        p.id === updatedParticipant.id ? updatedParticipant : p
      );
      setBill({ ...bill, participants: updatedParticipants });
    } catch (e) {
      console.error(e);
      alert('Failed to update status');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteParticipant = async (participantId: number) => {
    if (!currentUser) return;
    if (!confirm('Are you sure you want to remove this participant?')) return;
    
    try {
      setLoading(true);
      const updatedBill = await deleteBillParticipant(bill.id, participantId, currentUser.id);
      setBill(updatedBill);
    } catch (e) {
      console.error(e);
      alert('Failed to delete participant');
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
          myParticipation={myParticipation} 
          onMarkPaid={handleMarkPaid} 
          loading={loading} 
          hideAction={true}
        />
      )}

      {/* Participants Section */}
      <div>
        <div className="flex items-center justify-between mb-3 px-1">
          <h2 className="text-lg font-handwritten text-ink">Participants ({bill.participants.length})</h2>
          <Button size="sm" variant="ghost" onClick={() => setShowAddParticipant(true)}>
            <Plus className="w-4 h-4 mr-1" /> Add
          </Button>
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
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <p className="font-medium text-ink truncate text-sm">
                        {p.guest_name || `User #${p.user_id}`}
                      </p>
                      {!isOwner && (
                        <button
                          onClick={() => handleDeleteParticipant(p.id)}
                          className="p-1 text-ink/10 hover:text-red-500 transition-colors"
                          title="Remove participant"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                    <p className="text-xs text-ink/50">
                      {isOwner ? '👑 Owner' : p.is_paid ? 'Paid ✅' : 'Pending ⏳'}
                    </p>
                  </div>
                  {isOwner ? (
                    <button 
                      onClick={() => {
                        setAssigningId(p.id);
                        setAssignmentValue(p.allocated_amount.toString());
                      }}
                      className="text-[10px] uppercase font-bold text-accent hover:underline"
                    >
                      Assign
                    </button>
                  ) : (
                    <div className="flex flex-col items-end gap-1">
                      {p.is_paid ? (
                        <button 
                          onClick={() => handleTogglePaymentStatus(p.id, true)}
                          className="text-[10px] uppercase font-bold text-red-500 hover:underline"
                        >
                          Cancel
                        </button>
                      ) : (
                        <>
                          {!p.user_id && (
                            <button 
                              onClick={() => handleTogglePaymentStatus(p.id, false)}
                              className="text-[10px] uppercase font-bold text-green-600 hover:underline"
                            >
                              Confirm
                            </button>
                          )}
                          <button 
                            onClick={() => {
                              setAssigningId(p.id);
                              setAssignmentValue(p.allocated_amount.toString());
                            }}
                            className="text-[10px] uppercase font-bold text-accent hover:underline"
                          >
                            Assign
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              
              <div className="relative h-8 flex items-center justify-end overflow-hidden">
                <AnimatePresence mode="wait">
                  {assigningId === p.id ? (
                    <motion.div
                      key="assign-input"
                      initial={{ x: 50, opacity: 0 }}
                      animate={{ x: 0, opacity: 1 }}
                      exit={{ x: 50, opacity: 0 }}
                      className="absolute inset-0 flex items-center gap-1 bg-paper pl-1"
                    >
                      <input
                        type="text"
                        inputMode="decimal"
                        value={assignmentValue}
                        onChange={(e) => handleAssignmentInputChange(e.target.value)}
                        className="w-full text-right font-mono text-sm border-b border-accent focus:outline-none bg-transparent"
                        autoFocus
                      />
                      <button 
                        onClick={() => handleAssignAmount(p.id)}
                        className="p-1 text-green-600 hover:bg-green-50 rounded"
                      >
                        <Check className="w-4 h-4" />
                      </button>
                      <button 
                        onClick={() => setAssigningId(null)}
                        className="p-1 text-red-600 hover:bg-red-50 rounded"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </motion.div>
                  ) : (
                    <motion.div
                      key="amount-display"
                      initial={{ x: -20, opacity: 0 }}
                      animate={{ x: 0, opacity: 1 }}
                      exit={{ x: -20, opacity: 0 }}
                      className="flex items-center gap-2"
                    >
                      {!p.is_paid && p.allocated_amount > 0 && (
                        <button
                          onClick={() => {
                            setAssignmentValue('0');
                            handleAssignAmount(p.id);
                          }}
                          className="p-1 text-ink/20 hover:text-red-500 transition-colors"
                          title="Reset amount"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <span className="font-bold text-ink">
                        {formatCurrency(p.allocated_amount)}
                      </span>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
            );
          })}
          
          <motion.div
            layout
            onClick={() => setShowAddParticipant(true)}
            className="p-3 rounded-lg border-2 border-dashed border-ink/20 flex flex-col items-center justify-center min-h-[90px] cursor-pointer hover:bg-black/5 transition-colors"
          >
            <div className="w-8 h-8 rounded-full bg-ink/5 flex items-center justify-center mb-1">
              <Plus className="w-4 h-4 text-ink/40" />
            </div>
            <span className="text-xs text-ink/40 font-medium">Add Person</span>
          </motion.div>
        </div>
      </div>

      {/* Items Section */}
      <div>
        <div className="flex items-center justify-between mb-3 px-1">
          <h2 className="text-lg font-handwritten text-ink">Items ({bill.items.length})</h2>
          <Button size="sm" variant="ghost" onClick={() => setShowAddItem(true)}>
            <Plus className="w-4 h-4 mr-1" /> Add
          </Button>
        </div>

        <div className="space-y-2">
          {bill.items.length === 0 ? (
            <div className="text-center py-6 border-2 border-dashed border-ink/10 rounded-lg">
              <p className="text-ink/40 text-sm">No items added yet</p>
            </div>
          ) : (
            <>
              <div className="flex items-center px-3 py-1 text-[10px] uppercase font-bold text-ink/40 border-b border-ink/5 mb-1">
                <div className="flex-[3] min-w-0">Item</div>
                <div className="flex-1 text-center">Qty</div>
                <div className="flex-[2] text-right px-1">Price</div>
                <div className="flex-[2] text-right">Total</div>
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
        title="Add Participant"
        size="sm"
      >
        <div className="space-y-4">
          <Input 
            label="Name" 
            placeholder="Friend's Name" 
            value={newParticipantName}
            onChange={(e) => setNewParticipantName(e.target.value)}
          />
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={() => setShowAddParticipant(false)}>Cancel</Button>
            <Button onClick={handleAddParticipant} disabled={loading}>Add</Button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={showAddItem}
        onClose={() => setShowAddItem(false)}
        title="Add Item"
        size="sm"
      >
        <div className="space-y-4">
          <Input 
            label="Item Name" 
            placeholder="Pizza"
            value={newItemName}
            onChange={(e) => setNewItemName(e.target.value)}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input 
              label="Price" 
              type="text"
              inputMode="decimal"
              placeholder="0.00"
              value={newItemPrice}
              onChange={(e) => handleItemPriceChange(e.target.value)}
            />
            <Input 
              label="Count" 
              type="number"
              min="1"
              value={newItemCount}
              onChange={(e) => setNewItemCount(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={() => setShowAddItem(false)}>Cancel</Button>
            <Button onClick={handleAddItem} disabled={loading}>Add Item</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
