'use client';

import { BillDetail, BillStatus } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import { Copy, Check, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from '@/lib/i18n/useTranslation';

interface BillOverviewProps {
  bill: BillDetail;
  onSplitBetween?: (participantIds: number[]) => void;
  loading?: boolean;
}

export default function BillOverview({ bill, onSplitBetween, loading }: BillOverviewProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [showSelection, setShowSelection] = useState(false);
  
  // Default selected: all unpaid participants
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const handleToggleSelection = () => {
    const nextShow = !showSelection;
    setShowSelection(nextShow);
    
    if (nextShow) {
      // Initialize with unpaid participants
      const unpaid = bill.participants.filter(p => !p.is_paid).map(p => p.id);
      setSelectedIds(new Set(unpaid));
    }
  };

  // Stats
  const totalAmount = bill.total_sum;
  const itemsTotal = bill.items.reduce((sum, item) => sum + item.item_sum, 0); 
  const remainingTotal = bill.unallocated_sum;

  const handleCopyPayment = () => {
    if (bill.payment_details) {
      navigator.clipboard.writeText(bill.payment_details);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const toggleParticipant = (id: number) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  return (
    <div className="bg-paper shadow-md rounded-xl p-6 border-2 border-accent/20 relative overflow-hidden">
      <div className="absolute top-0 right-0 w-24 h-24 bg-accent/5 rounded-full -mr-8 -mt-8" />
      <div className="absolute bottom-0 left-0 w-16 h-16 bg-accent/5 rounded-full -ml-6 -mb-6" />
      
      <div className="relative z-10 text-center">
        {bill.status === BillStatus.PAID && (
          <motion.div 
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="mb-3 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-orange-500 text-white text-[10px] font-bold uppercase tracking-widest shadow-lg shadow-orange-500/20"
          >
            <div className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            {t('bill.statusPaid')}
          </motion.div>
        )}
        {bill.status === BillStatus.CLOSED && (
          <motion.div 
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="mb-3 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-green-500 text-white text-[10px] font-bold uppercase tracking-widest shadow-lg shadow-green-500/20"
          >
            <div className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            {t('bill.statusClosed')}
          </motion.div>
        )}
        <p className="text-ink/60 uppercase tracking-widest text-xs font-bold mb-1">{t('bill.totalBill')}</p>
        <div className="text-4xl font-bold text-accent font-handwritten">
          {formatCurrency(totalAmount)}
        </div>
        
        <div className="mt-4 flex justify-center gap-6 text-sm">
          <div>
            <p className="text-ink/50 text-xs text-ink/70">{t('bill.itemsTotal')}</p>
            <p className="font-medium text-ink">{formatCurrency(itemsTotal)}</p>
          </div>
          <div>
            <p className="text-ink/50 text-xs text-red-500">{t('bill.unallocated')}</p>
            <p className="font-medium text-red-500">{formatCurrency(remainingTotal)}</p>
          </div>
        </div>

        {/* Card Number / Payment Details */}
        {bill.payment_details && (
          <div className="mt-6 flex flex-col items-center">
            <p className="text-[10px] font-bold uppercase text-ink/40 mb-1">{t('bill.paymentCard')}</p>
            <div 
              className="flex items-center gap-2 bg-accent/5 px-4 py-2 rounded-full border border-accent/10 group active:scale-95 transition-transform cursor-pointer" 
              onClick={handleCopyPayment}
            >
              <code className="text-sm font-mono font-bold text-accent">{bill.payment_details}</code>
              {copied ? (
                <Check className="w-4 h-4 text-green-500" />
              ) : (
                <Copy className="w-4 h-4 text-accent/60 group-hover:text-accent" />
              )}
            </div>
          </div>
        )}

        {onSplitBetween && bill.participants.length > 0 && (
          <div className="mt-6 border-t border-accent/10 pt-4">
            <div className="flex flex-col gap-2">
              <div className="flex bg-white rounded-lg border border-accent/30 overflow-hidden shadow-sm">
                <button
                  onClick={() => onSplitBetween(Array.from(selectedIds))}
                  disabled={loading || selectedIds.size === 0 || remainingTotal === 0}
                  className="flex-1 px-4 py-2.5 text-xs font-bold text-accent hover:bg-accent/5 disabled:opacity-50 disabled:bg-white transition-colors border-r border-accent/30"
                >
                  {t('bill.splitEqually', { count: selectedIds.size.toString() })}
                </button>
                <button
                  onClick={handleToggleSelection}
                  className={`px-3 hover:bg-accent/5 transition-colors ${showSelection ? 'bg-accent/5' : ''}`}
                >
                  {showSelection ? <ChevronUp className="w-4 h-4 text-accent" /> : <ChevronDown className="w-4 h-4 text-accent" />}
                </button>
              </div>

              <AnimatePresence>
                {showSelection && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="mt-2 grid grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1 pb-1 custom-scrollbar">
                      {bill.participants.map(p => (
                        <label 
                          key={p.id} 
                          className={`
                            flex items-center gap-2 p-2 rounded-lg border transition-colors
                            ${p.is_paid 
                              ? 'bg-ink/5 border-transparent opacity-50 grayscale cursor-not-allowed' 
                              : selectedIds.has(p.id) 
                                ? 'bg-accent/5 border-accent/20 cursor-pointer' 
                                : 'bg-paper border-ink/5 cursor-pointer'}
                          `}
                        >
                          <input 
                            type="checkbox" 
                            disabled={p.is_paid}
                            checked={selectedIds.has(p.id)}
                            onChange={() => toggleParticipant(p.id)}
                            className="w-4 h-4 rounded border-ink/20 text-accent focus:ring-accent accent-accent"
                          />
                          <span className="text-[11px] font-medium text-ink truncate">
                            {p.guest_name || `User #${p.user_id}`}
                            {p.is_paid && ` ${t('bill.paidLabel')}`}
                          </span>
                        </label>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
