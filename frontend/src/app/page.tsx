'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Moon, Sun, Globe } from 'lucide-react';
import { useStore } from '@/lib/store/useStore';
import CreateBillModal from '@/components/bill/CreateBillModal';
import BillCard from '@/components/dashboard/BillCard';
import Button from '@/components/ui/Button';
import { motion } from 'framer-motion';
import { Bill } from '@/types/api';
import { createBill, addBillItem, addBillParticipant, getUserBills } from '@/lib/api/bills';
import FloatingCreateButton from '@/components/ui/FloatingCreateButton';
import { useRouter } from 'next/navigation';
import DevUserSwitcher from '@/components/ui/DevUserSwitcher';

interface BillSubmitData {
  title: string;
  total_sum: number;
  payment_details?: string;
  include_creator: boolean;
  items?: Array<{ name: string; price: number; count: number }>;
  participants?: string[];
}

const PAGE_SIZE = 10;

// Logic for scroll observer
function useIntersectionObserver(ref: React.RefObject<Element | null>, callback: () => void, enabled: boolean) {
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    if (!enabled || !ref.current) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          callback();
        }
      },
      { threshold: 0.5 }
    );

    observerRef.current.observe(ref.current);

    return () => {
      observerRef.current?.disconnect();
    };
  }, [ref, callback, enabled]);
}

export default function HomePage() {
  const router = useRouter();
  const { theme, toggleTheme, language, setLanguage, currentUser } = useStore();
  const [activeTab, setActiveTab] = useState<'active' | 'closed'>('active');
  const [showCreateModal, setShowCreateModal] = useState(false);
  
  const [activeBills, setActiveBills] = useState<Bill[]>([]);
  const [closedBills, setClosedBills] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  // Pagination state
  const [activePage, setActivePage] = useState(1);
  const [closedPage, setClosedPage] = useState(1);
  const [hasMoreActive, setHasMoreActive] = useState(true);
  const [hasMoreClosed, setHasMoreClosed] = useState(true);

  const loadMoreRef = useRef<HTMLDivElement>(null);

  const fetchBills = useCallback(async (page: number, tab: 'active' | 'closed', isInitial = false) => {
    if (!currentUser) return;
    
    try {
      if (isInitial) setLoading(true);
      else setLoadingMore(true);

      const bills = await getUserBills(currentUser.id, page, PAGE_SIZE);
      
      const filtered = bills.filter(b => tab === 'active' ? !b.is_closed : b.is_closed);
      const hasMore = bills.length === PAGE_SIZE;

      if (tab === 'active') {
        setActiveBills(prev => isInitial ? filtered : [...prev, ...filtered]);
        setHasMoreActive(hasMore);
      } else {
        setClosedBills(prev => isInitial ? filtered : [...prev, ...filtered]);
        setHasMoreClosed(hasMore);
      }
    } catch (error) {
      console.error('Error fetching bills:', error);
      if (tab === 'active') setHasMoreActive(false);
      else setHasMoreClosed(false);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [currentUser]);

  // Telegram Auto-Sync Logic
  useEffect(() => {
    const syncUser = async () => {
      if (typeof window === 'undefined') return;
      
      const { getTelegramUser } = await import('@/lib/telegram/init');
      const { getUserByTelegramId } = await import('@/lib/api/users');
      const tgUser = getTelegramUser();
      
      if (tgUser) {
        try {
          const syncedUser = await getUserByTelegramId(
            tgUser.id,
            tgUser.username || `${tgUser.first_name}${tgUser.last_name ? ' ' + tgUser.last_name : ''}`,
            tgUser.photo_url
          );
          if (syncedUser) {
            useStore.getState().setCurrentUser(syncedUser);
          }
        } catch (error) {
          console.error('Failed to sync Telegram user:', error);
        }
      }
    };

    syncUser();
  }, [currentUser?.id]); // Re-sync if id is missing or explicitly changed

  // Initial fetch on mount or user change
  useEffect(() => {
    const initFetch = async () => {
      try {
        setLoading(true);
        // Don't fetch bills until we have a user (either from store or synced)
        if (!currentUser) {
          setLoading(false);
          return;
        }
        
        const bills = await getUserBills(currentUser.id, 1, PAGE_SIZE);
        
        setActiveBills(bills.filter(b => !b.is_closed));
        setClosedBills(bills.filter(b => b.is_closed));
        
        const hasMore = bills.length === PAGE_SIZE;
        setHasMoreActive(hasMore);
        setHasMoreClosed(hasMore);
        
        setActivePage(1);
        setClosedPage(1);
      } catch (error) {
        console.error('Error fetching initial bills:', error);
        setActiveBills([]);
        setClosedBills([]);
        setHasMoreActive(false);
        setHasMoreClosed(false);
      } finally {
        setLoading(false);
      }
    };

    initFetch();
  }, [currentUser]);

  const loadMore = useCallback(() => {
    if (loading || loadingMore) return;
    
    if (activeTab === 'active' && hasMoreActive) {
      const nextPage = activePage + 1;
      setActivePage(nextPage);
      fetchBills(nextPage, 'active');
    } else if (activeTab === 'closed' && hasMoreClosed) {
      const nextPage = closedPage + 1;
      setClosedPage(nextPage);
      fetchBills(nextPage, 'closed');
    }
  }, [activeTab, activePage, closedPage, hasMoreActive, hasMoreClosed, loading, loadingMore, fetchBills]);

  // Custom hook usage
  useIntersectionObserver(
    loadMoreRef, 
    loadMore, 
    activeTab === 'active' ? hasMoreActive : hasMoreClosed
  );

  const handleCreateBill = () => {
    setShowCreateModal(true);
  };

  const handleBillSubmit = async (data: BillSubmitData) => {
    try {
      setLoading(true); // Optional: show loading state
      
      // 1. Create the bill
      const newBill = await createBill({
        title: data.title,
        total_sum: data.total_sum,
        owner_id: currentUser!.id, 
        payment_details: data.payment_details,
        include_owner: data.include_creator,
      });

      // 2. Add items
      if (data.items && data.items.length > 0) {
        for (const item of data.items) {
          await addBillItem(newBill.id, {
            name: item.name,
            price: item.price,
            count: item.count || 1,
          });
        }
      }

      // 3. Add participants
      // Filter out the creator if they are added manually, to avoid duplication if we handle include_creator separately
      // But based on CreateBillModal, strictly guests are in 'participants' array (strings)
      if (data.participants && data.participants.length > 0) {
        for (const guestName of data.participants) {
          await addBillParticipant(newBill.id, {
            guest_name: guestName,
            // owner_id is handled by backend or we invite users? 
            // The API expects BillParticipantCreate.
            // If it's a guest, we just send guest_name.
          });
        }
      }

      // 4. Creator is now handled by include_owner param in createBill

      setShowCreateModal(false);
      router.push(`/bill/${newBill.id}`);
      
    } catch (error) {
      console.error('Failed to create bill:', error);
      // TODO: Show error toast
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen notebook-page">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-paper/90 backdrop-blur-lg border-b-2 border-dashed border-accent/40 shadow-md">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <h1 className="text-2xl font-handwritten text-ink">
            Split The Bill 💰
          </h1>
          
          <div className="flex items-center gap-3">
            {/* User Profile */}
            {currentUser && (
              <div className="flex items-center gap-2 px-2 py-1 bg-paper-highlight border border-accent/20 rounded-full">
                {currentUser.avatar_url ? (
                  <img 
                    src={currentUser.avatar_url} 
                    alt={currentUser.username || ''} 
                    className="w-8 h-8 rounded-full border border-ink/10"
                  />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center border border-ink/10">
                    <span className="text-sm font-handwritten font-bold text-accent">
                      {(currentUser.username || 'U').charAt(0).toUpperCase()}
                    </span>
                  </div>
                )}
                <span className="hidden sm:block text-sm font-handwritten text-ink font-bold max-w-[100px] truncate">
                  {currentUser.username}
                </span>
              </div>
            )}

            {/* Dev User Switcher */}
            <DevUserSwitcher />

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
              className="rounded-full"
            >
              <Globe className="w-5 h-5" />
            </Button>
            
            {/* Theme Toggle */}
            <Button
              variant="ghost"
              size="sm"
              onClick={toggleTheme}
              className="rounded-full"
            >
              {theme === 'light' ? (
                <Moon className="w-5 h-5" />
              ) : (
                <Sun className="w-5 h-5" />
              )}
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 py-6">
        {loading ? (
          <div className="flex justify-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent"></div>
          </div>
        ) : (
          <>
            {/* Welcome Message */}
            {currentUser && (
              <motion.div
                className="mb-8 p-6 bg-paper-highlight border-2 border-dashed border-accent/30 rounded-lg"
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <h2 className="text-xl font-handwritten text-ink">
                  Welcome back, {currentUser.username || 'Friend'}! 👋
                </h2>
              </motion.div>
            )}

            {/* Tabs */}
            <div className="flex gap-6 mb-8 mt-4 border-b-2 border-accent/20 pb-1">
              <button
                onClick={() => setActiveTab('active')}
                className={`
                  px-6 py-3 font-handwritten text-xl transition-all relative
                  ${activeTab === 'active' 
                    ? 'text-accent font-bold' 
                    : 'text-ink/60 hover:text-ink hover:bg-paper-highlight/50 rounded-t-lg'
                  }
                `}
              >
                Active Bills 📝
                {activeTab === 'active' && (
                  <motion.div 
                    layoutId="activeTab"
                    className="absolute bottom-[-3px] left-0 right-0 h-1 bg-accent rounded-full"
                  />
                )}
              </button>
              <button
                onClick={() => setActiveTab('closed')}
                className={`
                  px-6 py-3 font-handwritten text-xl transition-all relative
                  ${activeTab === 'closed' 
                    ? 'text-accent font-bold' 
                    : 'text-ink/60 hover:text-ink hover:bg-paper-highlight/50 rounded-t-lg'
                  }
                `}
              >
                History 📚
                {activeTab === 'closed' && (
                  <motion.div 
                    layoutId="activeTab"
                    className="absolute bottom-[-3px] left-0 right-0 h-1 bg-accent rounded-full"
                  />
                )}
              </button>
            </div>

            {/* Bills List */}
            <div className="min-h-[500px]">
              {activeTab === 'active' && (
                <div>
                  {activeBills.length === 0 ? (
                    <motion.div
                      className="flex flex-col items-center justify-center py-24 px-4"
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                    >
                      <div className="bg-paper-highlight p-12 rounded-2xl border-2 border-dashed border-accent/30 shadow-sm max-w-md w-full flex flex-col items-center text-center transform rotate-1">
                        <div className="mt-2 space-y-2">
                          <p className="text-xl font-handwritten text-ink font-bold">
                            No active bills yet.
                          </p>
                          <p className="text-ink/60 font-handwritten text-lg">
                            Create your first bill to get started!
                          </p>
                        </div>
                      </div>
                    </motion.div>
                  ) : (
                    <div className="grid gap-6">
                      {activeBills.map(bill => (
                         <BillCard 
                           key={bill.id} 
                           bill={bill} 
                           role={bill.owner_id === currentUser?.id ? 'creator' : 'participant'} 
                         />
                      ))}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'closed' && (
                <div>
                  {closedBills.length === 0 ? (
                    <motion.div
                      className="flex flex-col items-center justify-center py-24 px-4"
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                    >
                      <div className="bg-paper-highlight p-12 rounded-2xl border-2 border-dashed border-accent/30 shadow-sm max-w-md w-full flex flex-col items-center text-center transform -rotate-1">
                        <div className="w-20 h-20 bg-paper border-2 border-ink rounded-full flex items-center justify-center mb-6">
                          <span className="text-4xl filter grayscale opacity-50">📭</span>
                        </div>
                        <p className="text-2xl font-handwritten text-ink font-bold">
                          No closed bills yet
                        </p>
                        <p className="mt-2 text-ink/60 font-handwritten text-lg">
                          Your completed bills will appear here
                        </p>
                      </div>
                    </motion.div>
                  ) : (
                    <div className="grid gap-6">
                      {closedBills.map(bill => (
                         <BillCard 
                           key={bill.id} 
                           bill={bill} 
                           role={bill.owner_id === currentUser?.id ? 'creator' : 'participant'} 
                         />
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Infinite Scroll Trigger */}
              <div ref={loadMoreRef} className="h-10 flex items-center justify-center mt-8">
                {loadingMore && (
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-accent"></div>
                )}
              </div>
            </div>
          </>
        )}
      </main>

      {/* Floating Create Button - Always visible */}
      <FloatingCreateButton 
        onClick={handleCreateBill} 
        show={true} 
      />

      {/* Create Bill Modal */}
      <CreateBillModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSubmit={handleBillSubmit}
      />
    </div>
  );
}
