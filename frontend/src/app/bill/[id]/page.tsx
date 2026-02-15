'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useStore } from '@/lib/store/useStore';
import { getBill, generateTelegramShareLink } from '@/lib/api/bills';
import { BillDetail } from '@/types/api';
import Button from '@/components/ui/Button';
import { ChevronLeft, Share2, Loader2, Moon, Sun, Globe } from 'lucide-react';
import { motion } from 'framer-motion';
import BillDetailsCreator from '@/components/bill/BillDetailsCreator';
import BillDetailsParticipant from '@/components/bill/BillDetailsParticipant';
import { showBackButton, hideBackButton, shareLink } from '@/lib/telegram/init';
import { useBillEvents } from '@/hooks/useBillEvents';

export default function BillPage() {
  const params = useParams();
  const router = useRouter();
  const { id } = params;
  const { currentUser, theme, toggleTheme, language, setLanguage } = useStore();
  
  const [bill, setBill] = useState<BillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeReactions, setActiveReactions] = useState<Record<number, string>>({});

  const reactionTimeoutsRef = useRef<Record<number, NodeJS.Timeout>>({});
  const handleReaction = useCallback((userId: number, emoji: string) => {
    // Clear existing timeout for this user if any
    if (reactionTimeoutsRef.current[userId]) {
      clearTimeout(reactionTimeoutsRef.current[userId]);
    }

    // Set unique reaction with timestamp to trigger re-animation
    const uniqueReaction = `${emoji}|${Date.now()}`;
    setActiveReactions(prev => ({ ...prev, [userId]: uniqueReaction }));

    // Clear the reaction after 3 seconds
    reactionTimeoutsRef.current[userId] = setTimeout(() => {
      setActiveReactions(prev => {
        const next = { ...prev };
        delete next[userId];
        return next;
      });
      delete reactionTimeoutsRef.current[userId];
    }, 3000);
  }, []);

  useEffect(() => {
    // Show Telegram back button
    showBackButton(() => {
      router.push('/');
    });

    return () => {
      hideBackButton();
    };
  }, [router]);

  const fetchBill = useCallback(async (showLoading = false) => {
    if (!id) return;
    
    try {
      if (showLoading) setLoading(true);
      const billId = parseInt(Array.isArray(id) ? id[0] : id);
      if (isNaN(billId)) throw new Error('Invalid bill ID');
      
      const data = await getBill(billId);
      setBill(data);
    } catch (err: unknown) {
      console.error('Error fetching bill:', err);
      if (showLoading) setError(err instanceof Error ? err.message : 'Failed to load bill');
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchBill(true);
  }, [fetchBill]);

  // Subscribe to real-time events
  useBillEvents(bill?.id, fetchBill, handleReaction);

  if (loading) {
    return (
      <div className="min-h-screen notebook-page flex items-center justify-center flex-col gap-4">
        <Loader2 className="w-8 h-8 text-accent animate-spin" />
        <p className="font-handwritten text-xl text-ink/60">Finding your bill...</p>
      </div>
    );
  }

  if (error || !bill) {
    return (
      <div className="min-h-screen notebook-page flex items-center justify-center flex-col p-6 text-center">
        <div className="text-4xl mb-4">😰</div>
        <h2 className="font-handwritten text-2xl text-ink mb-2">Oops! Something went wrong</h2>
        <p className="text-ink/60 mb-6">{error || 'Bill not found'}</p>
        <Button onClick={() => router.push('/')}>Go Back Home</Button>
      </div>
    );
  }

  // Determine view mode
  if (!currentUser) {
    return (
      <div className="min-h-screen notebook-page flex items-center justify-center flex-col gap-4">
        <Loader2 className="w-8 h-8 text-accent animate-spin" />
        <p className="font-handwritten text-xl text-ink/60">Waiting for user session...</p>
      </div>
    );
  }

  const isCreator = currentUser.id === bill.owner_id;

  return (
    <div className="min-h-screen notebook-page pb-12">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-paper/90 backdrop-blur-lg border-b border-accent/20">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <button 
            onClick={() => router.push('/')}
            className="p-2 -ml-2 hover:bg-black/5 rounded-full transition-colors"
          >
            <ChevronLeft className="w-6 h-6 text-ink" />
          </button>
          
          <h1 className="font-handwritten text-xl text-ink truncate max-w-[200px]">
            {bill.title || 'Bill Details'}
          </h1>
          
          <div className="flex items-center gap-1">
            {/* Language Toggle */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                const langs: Array<'en' | 'ru' | 'uz'> = ['en', 'ru', 'uz'];
                const currentIndex = langs.indexOf(language);
                const nextLang = langs[(currentIndex + 1) % langs.length];
                setLanguage(nextLang);
              }}
              className="rounded-full flex items-center gap-1 px-3"
            >
              <Globe className="w-5 h-5" />
              <span className="text-xs font-bold uppercase">{language}</span>
            </Button>
            
            <Button
              variant="ghost"
              size="sm"
              onClick={toggleTheme}
              className="rounded-full"
            >
              {theme === 'light' ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
            </Button>

            <button 
              onClick={() => {
                const link = generateTelegramShareLink(bill.id, bill.title || '');
                shareLink(link);
              }}
              className="p-2 hover:bg-black/5 rounded-full transition-colors text-accent"
            >
              <Share2 className="w-6 h-6" />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {isCreator ? (
            <BillDetailsCreator 
              bill={bill} 
              setBill={setBill} 
              currentUser={currentUser}
              reactions={activeReactions}
            />
          ) : (
            <BillDetailsParticipant 
              bill={bill} 
              currentUser={currentUser}
              setBill={setBill} 
              reactions={activeReactions}
            />
          )}
        </motion.div>
      </main>
    </div>
  );
}
