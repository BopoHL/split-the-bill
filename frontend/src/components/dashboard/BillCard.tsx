'use client';

import { motion } from 'framer-motion';
import { Users, ChevronRight, CheckCircle2, Clock } from 'lucide-react';
import { formatCurrency } from '@/lib/utils/currency';
import type { Bill } from '@/types/api';
import { useRouter } from 'next/navigation';

import { useTranslation } from '@/lib/i18n/useTranslation';

interface BillCardProps {
  bill: Bill;
  role: 'creator' | 'participant';
}

export default function BillCard({ bill, role }: BillCardProps) {
  const router = useRouter();
  const { t } = useTranslation();

  const handleClick = () => {
    router.push(`/bill/${bill.id}`);
  };

  const participantCount = bill.participants_count || 0;
  const isPaid = bill.is_closed;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      whileHover={{ scale: 1.02, rotate: -1 }}
      whileTap={{ scale: 0.98 }}
      onClick={handleClick}
      className={`
        relative p-4 rounded-lg cursor-pointer
        bg-paper border-2 border-accent/20
        shadow-sm hover:shadow-md transition-all
        group
      `}
    >
      <div className={`
        absolute -top-3 -right-2 px-3 py-1 rounded-full text-xs font-bold shadow-sm transform rotate-3
        ${role === 'creator' 
          ? 'bg-accent text-white' 
          : 'bg-paper-highlight text-ink border border-accent/30'
        }
      `}>
        {role === 'creator' 
          ? `👑 ${t('bill.creatorRole')}` 
          : `👤 ${t('bill.guestRole')}`
        }
      </div>

      <div className="flex justify-between items-start mb-2">
        <div>
          <h3 className="font-handwritten text-xl text-ink group-hover:text-accent transition-colors">
            {bill.title || 'Untitled Bill'}
          </h3>
          <p className="text-xs text-ink/50 font-mono">
            {new Date(bill.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="text-right mt-1">
          <p className="font-bold text-lg text-ink">
            {formatCurrency(bill.total_sum)}
          </p>
          {bill.unallocated_sum > 0 && !bill.is_closed && (
            <p className="text-[10px] font-bold text-red-500 uppercase tracking-tighter">
              {t('bill.left', { amount: formatCurrency(bill.unallocated_sum) })}
            </p>
          )}
        </div>
      </div>

      <div className="h-px bg-accent/10 w-full my-3 border-b border-dashed border-accent/30" />

      <div className="flex justify-between items-center text-sm text-ink/70">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5" title="Participants">
            <Users className="w-4 h-4" />
            <span>{participantCount}</span>
          </div>
          
          <div className={`flex items-center gap-1.5 ${isPaid ? 'text-green-600' : 'text-orange-600'}`}>
            {isPaid ? (
              <>
                <CheckCircle2 className="w-4 h-4" />
                <span>{t('bill.statusClosed')}</span>
              </>
            ) : (
              <>
                <Clock className="w-4 h-4" />
                <span>{t('bill.statusActive')}</span>
              </>
            )}
          </div>
        </div>

        <ChevronRight className="w-5 h-5 text-accent/50 group-hover:translate-x-1 transition-transform" />
      </div>
    </motion.div>
  );
}
