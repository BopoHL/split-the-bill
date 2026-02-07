'use client';

import { useState } from 'react';
import { Shield, Check } from 'lucide-react';
import { useStore } from '@/lib/store/useStore';
import Button from '@/components/ui/Button';
import { AnimatePresence, motion } from 'framer-motion';

/**
 * DEV-ONLY COMPONENT: Used to switch current user ID for testing.
 * TODO: REMOVE BEFORE PRODUCTION
 */
export default function DevUserSwitcher() {
  const { currentUser, setCurrentUser } = useStore();
  const [isOpen, setIsOpen] = useState(false);
  const [newUserId, setNewUserId] = useState(currentUser?.id?.toString() || '');

  const handleSwitch = () => {
    const id = parseInt(newUserId);
    if (!isNaN(id)) {
      setCurrentUser({
        id,
        telegram_id: 1000000 + id,
        username: `Dev User ${id}`,
        avatar_url: null
      });
      setIsOpen(false);
    }
  };

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsOpen(!isOpen)}
        className={`rounded-full ${isOpen ? 'bg-accent/10 text-accent' : 'text-ink/30 hover:text-ink'}`}
        title="Switch User (Dev Only)"
      >
        <Shield className="w-5 h-5" />
      </Button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="absolute right-0 mt-2 p-4 bg-paper border-2 border-accent shadow-xl rounded-xl z-50 w-48"
          >
            <div className="space-y-3">
              <p className="text-xs font-bold uppercase tracking-widest text-accent mb-2">Dev Switcher</p>
              <div className="flex flex-col gap-2">
                <label className="text-[10px] font-bold text-ink/40 uppercase">User ID</label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={newUserId}
                    onChange={(e) => setNewUserId(e.target.value)}
                    className="w-full bg-paper-highlight border-b border-accent px-1 py-1 text-sm focus:outline-none font-mono"
                    autoFocus
                  />
                  <button
                    onClick={handleSwitch}
                    className="p-1 bg-accent text-white rounded hover:bg-accent/80"
                  >
                    <Check className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <p className="text-[10px] text-ink/40 leading-tight italic">
                Current ID: {currentUser?.id || 'none'}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
