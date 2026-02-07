'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useStore } from '@/lib/store/useStore';
import { getBill } from '@/lib/api/bills';
import { BillDetail } from '@/types/api';
import Button from '@/components/ui/Button';
import { ChevronLeft, Share2, Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';
import BillDetailsCreator from '@/components/bill/BillDetailsCreator';
import BillDetailsParticipant from '@/components/bill/BillDetailsParticipant';
import { showBackButton, hideBackButton, shareLink } from '@/lib/telegram/init';
import DevUserSwitcher from '@/components/ui/DevUserSwitcher';

export default function BillPage() {
  const params = useParams();
  const router = useRouter();
  const { id } = params;
  const { currentUser } = useStore();
  
  const [bill, setBill] = useState<BillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Show Telegram back button
    showBackButton(() => {
      router.push('/');
    });

    return () => {
      hideBackButton();
    };
  }, [router]);

  useEffect(() => {
    const fetchBill = async () => {
      if (!id) return;
      
      try {
        setLoading(true);
        // Cast id to number safely
        const billId = parseInt(Array.isArray(id) ? id[0] : id);
        if (isNaN(billId)) throw new Error('Invalid bill ID');
        
        const data = await getBill(billId);
        setBill(data);
      } catch (err: unknown) {
        console.error('Error fetching bill:', err);
        setError(err instanceof Error ? err.message : 'Failed to load bill');
      } finally {
        setLoading(false);
      }
    };

    fetchBill();
  }, [id]);

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
  // The user is a creator if their telegram_id matches the bill owner's
  // Since we might not have the full user objects fully populated yet, we rely on logic:
  // We need to fetch the owner user details or store current user telegram_id in a robust way.
  // For now, assuming currentUser.id matches bill.owner_id is the check.
  // Fallback to ID 1 in dev environment if currentUser is not set
  const currentUserId = currentUser?.id || 1;
  const isCreator = currentUserId === bill.owner_id;

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
            <DevUserSwitcher />
            <button 
              onClick={() => {
                const link = `${window.location.origin}/join/${bill.id}`;
                shareLink(`https://t.me/share/url?url=${link}&text=Join my bill!`);
              }}
              className="p-2 -mr-2 hover:bg-black/5 rounded-full transition-colors text-accent"
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
              currentUser={currentUser || { id: 1, telegram_id: 123456, username: 'Dev User', avatar_url: null }} 
            />
          ) : (
            <BillDetailsParticipant 
              bill={bill} 
              currentUser={currentUser || { id: 1, telegram_id: 123456, username: 'Dev User', avatar_url: null }} 
              setBill={setBill} 
            />
          )}
        </motion.div>
      </main>
    </div>
  );
}
