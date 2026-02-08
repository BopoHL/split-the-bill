import { formatCurrency } from '@/lib/utils/currency';
import Button from '@/components/ui/Button';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Copy } from 'lucide-react';
import { BillParticipant } from '@/types/api';
import { useState } from 'react';
import { sendReaction } from '@/lib/api/bills';

interface YouShareBlockProps {
  billId: number;
  myParticipation: BillParticipant;
  onMarkPaid: () => void;
  loading: boolean;
  hideAction?: boolean;
}

import { useTranslation } from '@/lib/i18n/useTranslation';

export default function YouShareBlock({ billId, myParticipation, onMarkPaid, loading, hideAction }: YouShareBlockProps) {
  const { t } = useTranslation();
  const isPaid = myParticipation.is_paid;
  const myAmount = myParticipation.allocated_amount;
  const [copied, setCopied] = useState(false);
  const [sendingReaction, setSendingReaction] = useState<string | null>(null);

  const handleCopyAmount = () => {
    navigator.clipboard.writeText(myAmount.toString());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleEmojiClick = async (emoji: string) => {
    if (!myParticipation.user_id) return;
    try {
      setSendingReaction(emoji);
      await sendReaction(billId, myParticipation.user_id, emoji);
      setTimeout(() => setSendingReaction(null), 500);
    } catch (e) {
      console.error('Failed to send reaction:', e);
      setSendingReaction(null);
    }
  };

  const reactions = [
    { emoji: '😊', label: 'Smiling' },
    { emoji: '😎', label: 'Cool' },
    { emoji: '😱', label: 'Shocked' }
  ];

  return (
    <div className="space-y-4">
      <div className={`
        relative overflow-hidden rounded-xl p-6 border-2 shadow-lg transition-all
        ${isPaid 
          ? 'bg-green-50 border-green-200 dark:bg-green-900/10 dark:border-green-800' 
          : 'bg-paper border-accent'
        }
      `}>
        <div className="text-center relative z-10">
          <p className="text-sm font-medium uppercase tracking-wider mb-2 opacity-70">
            {isPaid ? t('bill.youPaid') : t('bill.yourShare')}
          </p>
          
          <div className="flex items-center justify-center gap-2 group">
            <div className="text-5xl font-handwritten font-bold mb-1 text-ink">
              {formatCurrency(myAmount)}
            </div>
            
            {!isPaid && (
              <button
                onClick={handleCopyAmount}
                className="p-2 rounded-full hover:bg-accent/5 transition-colors group-active:scale-90"
                title={t('common.copy')}
              >
                {copied ? (
                  <Check className="w-5 h-5 text-green-500" />
                ) : (
                  <Copy className="w-5 h-5 text-accent/40 group-hover:text-accent transition-colors" />
                )}
              </button>
            )}
          </div>
          
          <div className="flex justify-center gap-4 mt-4">
            {reactions.map(({ emoji }) => (
              <motion.button
                key={emoji}
                whileTap={{ scale: 1.5 }}
                onClick={() => handleEmojiClick(emoji)}
                className="text-2xl hover:bg-paper-highlight p-2 rounded-full transition-colors active:scale-125"
                disabled={sendingReaction === emoji}
              >
                {emoji}
              </motion.button>
            ))}
          </div>
          
          <AnimatePresence>
            {isPaid && (
              <motion.div 
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                className="mt-4 inline-flex items-center gap-2 px-3 py-1 bg-green-200/50 text-green-800 rounded-full text-sm font-medium"
              >
                <Check className="w-4 h-4" /> {t('bill.paidLabel')}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {myAmount > 0 && !isPaid && !hideAction && (
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
        >
          <Button 
            className="w-full py-4 text-lg shadow-lifted" 
            onClick={onMarkPaid}
            disabled={loading}
          >
            {t('bill.iPaid', { amount: formatCurrency(myAmount) })}
          </Button>
          <p className="text-center text-xs text-ink/40 mt-3 px-4">
            {t('bill.clickAfterTransfer')}
          </p>
        </motion.div>
      )}
    </div>
  );
}
