'use client';

import { motion } from 'framer-motion';
import { Plus } from 'lucide-react';

interface CircleButtonProps {
  onClick: () => void;

  icon?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg';
}

const sizes = {
  sm: 'w-14 h-14',
  md: 'w-20 h-20',
  lg: 'w-24 h-24',
};

const iconSizes = {
  sm: 'w-5 h-5',
  md: 'w-6 h-6',
  lg: 'w-8 h-8',
};

export const CircleButton = ({ 
  onClick, 
  icon,
  size = 'md'
}: CircleButtonProps) => {
  return (
    <motion.button
      onClick={onClick}
      className={`
        ${sizes[size]}
        relative flex flex-col items-center justify-center
        bg-paper border-[3px] border-ink
        font-handwritten text-ink
        cursor-pointer select-none
        transition-colors
        hover:bg-paper-highlight
      `}
      style={{
        borderRadius: '42% 48% 45% 52% / 52% 45% 48% 42%',
      }}
      whileHover={{ 
        scale: 1.08,
        rotate: 2,
        boxShadow: 'var(--shadow-lifted)'
      }}
      whileTap={{ scale: 0.95 }}
      initial={{ scale: 0, rotate: -10 }}
      animate={{ scale: 1, rotate: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
    >
      {icon || <Plus className={iconSizes[size]} />}
    </motion.button>
  );
};

export const CreateBillButton = ({ onClick }: { onClick: () => void }) => {
  return (
    <motion.div
      className="flex flex-col items-center gap-5"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
    >
      <CircleButton onClick={onClick} size="lg" />
      <button 
        onClick={onClick}
        className="font-handwritten text-lg text-ink hover:text-accent transition-colors"
      >
        + Create New Bill
      </button>
    </motion.div>
  );
};
