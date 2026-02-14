'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { BillParticipant } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { Trash2 } from 'lucide-react';

interface ParticipantCardProps {
  participant: BillParticipant;
  isOwner: boolean;
  reaction?: string;
  onDelete?: (id: number) => void;
  onTogglePayment?: (id: number, currentPaid: boolean) => void;
  onAssignAmount?: (id: number, amount: number) => Promise<void>;
  isCreatorView?: boolean;
  isClosed?: boolean;
}

import { useState } from 'react';
import { Check, X } from 'lucide-react';
import { displayToAmount } from '@/lib/utils/currency';

export default function ParticipantCard({
  participant,
  isOwner,
  reaction,
  onDelete,
  onTogglePayment,
  onAssignAmount,
  isCreatorView,
  isClosed
}: ParticipantCardProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const p = participant;

  const handleStartEdit = () => {
    setEditValue(p.allocated_amount.toString());
    setIsEditing(true);
  };

  const handleSave = async () => {
    const amount = displayToAmount(editValue);
    if (!isNaN(amount) && onAssignAmount) {
      await onAssignAmount(p.id, amount);
      setIsEditing(false);
    }
  };

  return (
    <motion.div
      layout
      className={`
        relative p-3 rounded-lg border-2 transition-all duration-300
        ${isOwner 
          ? 'border-accent/40 bg-accent/5' 
          : p.is_paid 
            ? 'bg-green-50 border-green-200 dark:bg-green-900/10 dark:border-green-800' 
            : 'bg-paper border-ink/10'
        }
      `}
    >
      {/* Reaction Animation */}
      <AnimatePresence>
        {reaction && (
          <motion.div
            key={reaction}
            initial={{ scale: 0, y: 0, opacity: 0 }}
            animate={{ scale: [0, 2, 2, 0], y: -50, opacity: [0, 1, 1, 0] }}
            transition={{ duration: 2, ease: "easeOut" }}
            className="absolute inset-x-0 top-0 flex justify-center z-50 pointer-events-none"
          >
            <span className="text-4xl">{reaction}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex justify-between items-start mb-2">
        <div className="flex-1 min-w-0 pr-2">
          <div className="flex items-center gap-1.5 mb-0.5">
            <div className="w-7 h-7 rounded-full overflow-hidden border border-ink/10 flex-shrink-0 bg-accent/20">
              {p.avatar_url ? (
                <img src={p.avatar_url} alt={p.name || p.username || ''} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-paper-highlight text-[10px] font-bold text-accent">
                  {(p.name || p.username || p.guest_name || 'U').charAt(0).toUpperCase()}
                </div>
              )}
            </div>
            <p className="font-medium text-ink break-words text-sm leading-tight">
              {p.name || p.surname 
                ? `${p.name || ''} ${p.surname || ''}`.trim() 
                : p.username || p.guest_name || `User #${p.user_id}`}
            </p>
            {isCreatorView && !isOwner && onDelete && (
              <button
                onClick={() => onDelete(p.id)}
                className="p-1 text-ink/10 hover:text-red-500 transition-colors"
                title={t('common.delete')}
              >
                <Trash2 className="w-3 h-3" />
              </button>
            )}
          </div>
          <p className="text-xs text-ink/50">
            {isOwner ? `👑 ${t('bill.creatorRole')}` : p.is_paid ? `${t('bill.paidLabel')} ✅` : `${t('bill.statusActive')} ⏳`}
          </p>
        </div>

        {isCreatorView && !isClosed && (
          <div className="flex flex-col items-end gap-1">
            {isOwner ? (
              onAssignAmount && (
                <button 
                  onClick={handleStartEdit}
                  className="text-[10px] uppercase font-bold text-accent hover:underline"
                >
                  {t('bill.assign')}
                </button>
              )
            ) : (
              <>
                {p.is_paid ? (
                  onTogglePayment && (
                    <button 
                      onClick={() => onTogglePayment(p.id, true)}
                      className="text-[10px] uppercase font-bold text-red-500 hover:underline"
                    >
                      {t('common.cancel')}
                    </button>
                  )
                ) : (
                  <>
                    {!p.user_id && onTogglePayment && (
                      <button 
                        onClick={() => onTogglePayment(p.id, false)}
                        className="text-[10px] uppercase font-bold text-green-600 hover:underline"
                      >
                        {t('common.confirm')}
                      </button>
                    )}
                    {onAssignAmount && (
                      <button 
                        onClick={handleStartEdit}
                        className="text-[10px] uppercase font-bold text-accent hover:underline"
                      >
                        {t('bill.assign')}
                      </button>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        )}
      </div>
      
      <div className="relative h-8 flex items-center justify-end overflow-hidden">
        <AnimatePresence mode="wait">
          {isEditing ? (
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
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                className="w-full text-right font-mono text-sm border-b border-accent focus:outline-none bg-transparent"
                autoFocus
              />
              <button 
                onClick={handleSave}
                className="p-1 text-green-600 hover:bg-green-50 rounded"
              >
                <Check className="w-4 h-4" />
              </button>
              <button 
                onClick={() => setIsEditing(false)}
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
              {!p.is_paid && p.allocated_amount > 0 && isCreatorView && !isClosed && (
                <button
                  onClick={() => {
                    const confirmCancel = confirm(t('bill.cancelAllocationAlert') || 'Cancel allocation?');
                    if (confirmCancel && onAssignAmount) onAssignAmount(p.id, 0);
                  }}
                  className="p-1 text-ink/20 hover:text-red-500 transition-colors"
                  title={t('common.cancel')}
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
}
