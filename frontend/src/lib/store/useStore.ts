import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, BillDetail } from '@/types/api';

interface AppState {
  // User state
  currentUser: User | null;
  setCurrentUser: (user: User | null) => void;
  
  // Theme state
  theme: 'light' | 'dark';
  setTheme: (theme: 'light' | 'dark') => void;
  toggleTheme: () => void;
  
  // Language state
  language: 'en' | 'ru' | 'uz';
  setLanguage: (language: 'en' | 'ru' | 'uz') => void;
  
  // Bills cache
  bills: BillDetail[];
  addBill: (bill: BillDetail) => void;
  updateBill: (billId: number, bill: BillDetail) => void;
  removeBill: (billId: number) => void;
  clearBills: () => void;
  
  // Current bill
  currentBill: BillDetail | null;
  setCurrentBill: (bill: BillDetail | null) => void;
  
  // Loading states
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      // User state
      currentUser: null,
      setCurrentUser: (user) => set({ currentUser: user }),
      
      // Theme state
      theme: 'light',
      setTheme: (theme) => set({ theme }),
      toggleTheme: () =>
        set((state) => ({ theme: state.theme === 'light' ? 'dark' : 'light' })),
      
      // Language state
      language: 'en',
      setLanguage: (language) => set({ language }),
      
      // Bills cache
      bills: [],
      addBill: (bill) =>
        set((state) => ({
          bills: [...state.bills, bill],
        })),
      updateBill: (billId, bill) =>
        set((state) => ({
          bills: state.bills.map((b) => (b.id === billId ? bill : b)),
        })),
      removeBill: (billId) =>
        set((state) => ({
          bills: state.bills.filter((b) => b.id !== billId),
        })),
      clearBills: () => set({ bills: [] }),
      
      // Current bill
      currentBill: null,
      setCurrentBill: (bill) => set({ currentBill: bill }),
      
      // Loading states
      isLoading: false,
      setIsLoading: (loading) => set({ isLoading: loading }),
    }),
    {
      name: 'split-the-bill-storage',
      partialize: (state) => ({
        theme: state.theme,
        language: state.language,
        currentUser: state.currentUser,
      }),
    }
  )
);
