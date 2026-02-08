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
  onAssign?: (id: number, currentAmount: number) => void;
  isCreatorView?: boolean;
}

export default function ParticipantCard({
  participant,
  isOwner,
  reaction,
  onDelete,
  onTogglePayment,
  onAssign,
  isCreatorView
}: ParticipantCardProps) {
  const { t } = useTranslation();
  const p = participant;

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
                <img src={p.avatar_url} alt={p.username || ''} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-paper-highlight text-[10px] font-bold text-accent">
                  {(p.username || p.guest_name || 'U').charAt(0).toUpperCase()}
                </div>
              )}
            </div>
            <p className="font-medium text-ink truncate text-sm">
              {p.username || p.guest_name || `User #${p.user_id}`}
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

        {isCreatorView && (
          <div className="flex flex-col items-end gap-1">
            {isOwner ? (
              onAssign && (
                <button 
                  onClick={() => onAssign(p.id, p.allocated_amount)}
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
                    {onAssign && (
                      <button 
                        onClick={() => onAssign(p.id, p.allocated_amount)}
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
        <div className="font-bold text-ink">
          {formatCurrency(p.allocated_amount)}
        </div>
      </div>
    </motion.div>
  );
}
