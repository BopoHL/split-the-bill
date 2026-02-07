import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CircleButton } from './CircleButton';

interface FloatingCreateButtonProps {
  onClick: () => void;
  show?: boolean;
}

export default function FloatingCreateButton({ onClick, show = true }: FloatingCreateButtonProps) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
           className="fixed bottom-8 right-8 z-50 pointer-events-auto"
           initial={{ scale: 0, rotate: 180 }}
           animate={{ scale: 1, rotate: 0 }}
           exit={{ scale: 0, rotate: -180 }}
           whileHover={{ scale: 1.1 }}
           whileTap={{ scale: 0.9 }}
        >
          <CircleButton 
            onClick={onClick} 
            size="lg" // Match the large size of the original button
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
