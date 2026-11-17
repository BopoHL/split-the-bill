'use client';

import { useState, useEffect, useCallback } from 'react';
import { Archive, ChartColumn, GraduationCap, Plus, Receipt } from 'lucide-react';
import { useStore } from '@/lib/store/useStore';
import CreateBillWizard, { type BillCreateSubmit } from '@/components/bill/create/CreateBillWizard';
import ActivePanel from '@/components/dashboard/ActivePanel';
import ArchivePanel from '@/components/dashboard/ArchivePanel';
import AnalyticsPanel from '@/components/analytics/AnalyticsPanel';
import OwedCard from '@/components/dashboard/OwedCard';
import Button from '@/components/ui/Button';
import ProfileChip from '@/components/profile/ProfileChip';
import ProButton from '@/components/pro/ProButton';
import SettingsMenu from '@/components/ui/SettingsMenu';
import { motion } from 'framer-motion';
import { Bill } from '@/types/api';
import {
  createBill,
  getUserBills,
  deleteBill,
  updatePaymentStatus,
} from '@/lib/api/bills';
import { sendReminders } from '@/lib/api/reminders';
import { useArchive } from '@/hooks/useArchive';
import { translateApiError } from '@/lib/utils/apiError';
import FloatingCreateButton from '@/components/ui/FloatingCreateButton';
import SwipeTabs from '@/components/ui/SwipeTabs';
import HomeScreenBanner from '@/components/ui/HomeScreenBanner';
import LanguageStep from '@/components/onboarding/LanguageStep';
import { TourAnchor } from '@/lib/tour/anchors';
import { useTour } from '@/lib/tour/useTour';
import { useInvitePrompt } from '@/lib/store/useInvitePrompt';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import AppHeader from '@/components/layout/AppHeader';
import { track, AnalyticsEvent } from '@/lib/analytics';

// Active bills are fetched once with a generous cap — there are usually
// few of them. The archive pages itself in.
const ACTIVE_LIMIT = 100;
const MIN_RECHECK_MS = 15_000;

type HomeTab = 'active' | 'archive' | 'analytics';

const countBadge = (count: number) => String(count).padStart(2, '0');

const apiDetail = (error: unknown) =>
  (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

// Empty-state enter: split into icon/title/description and stagger each so the
// prompt assembles itself instead of fading in as one block.
const EMPTY_STAGGER = {
  visible: { transition: { staggerChildren: 0.1 } },
};
const EMPTY_ITEM = {
  hidden: { opacity: 0, y: 12, filter: 'blur(4px)' },
  visible: { opacity: 1, y: 0, filter: 'blur(0px)' },
};

export default function HomePage() {
  const router = useRouter();
  const { currentUser } = useStore();
  const { t } = useTranslation();
  const tourRunning = useTour((state) => state.active);
  const arriving = useTour((state) => state.arriving);
  const startTour = useTour((state) => state.start);
  const completeOnboarding = useStore((state) => state.completeOnboarding);

  // First run: the language, and then home, where the way to start is — the
  // tour is offered there, not walked through unasked: most of those it was
  // put in front of straight away skipped it.
  const [languageChosen, setLanguageChosen] = useState(false);
  const welcomeDue =
    !!currentUser
    && currentUser.settings?.onboarding_completed !== true
    && !arriving
    && !tourRunning;
  // A guest has had the app in their Telegram's language since they joined:
  // the tour goes straight on.
  const cameAsGuest = currentUser?.settings?.guest_tour_completed === true;
  const showLanguageStep = welcomeDue && !cameAsGuest && !languageChosen;

  const finishOnboarding = useCallback(() => {
    void completeOnboarding().then((saved) => {
      if (saved) track(AnalyticsEvent.OnboardingCompleted, { language: useStore.getState().language });
    });
  }, [completeOnboarding]);

  useEffect(() => {
    if (welcomeDue && cameAsGuest) finishOnboarding();
  }, [welcomeDue, cameAsGuest, finishOnboarding]);

  const handleLanguageChosen = () => {
    setLanguageChosen(true);
    finishOnboarding();
  };
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createSession, setCreateSession] = useState(0);

  const [activeBills, setActiveBills] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTab, setSelectedTab] = useState<HomeTab>('active');
  // Bumped whenever what others owe may have changed, so «Owed to you» re-asks.
  const [owedVersion, setOwedVersion] = useState(0);
  const archive = useArchive(currentUser?.id);

  const loadActive = useCallback(async () => {
    if (!currentUser) return;
    try {
      setActiveBills(await getUserBills(currentUser.id, 0, ACTIVE_LIMIT, 'active'));
    } catch (error) {
      console.error('Error fetching bills:', error);
    }
  }, [currentUser]);

  useEffect(() => {
    if (!currentUser) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    getUserBills(currentUser.id, 0, ACTIVE_LIMIT, 'active')
      .then((active) => {
        if (!cancelled) setActiveBills(active);
      })
      .catch((error) => {
        console.error('Error fetching bills:', error);
        if (!cancelled) setActiveBills([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [currentUser]);

  // A bell rests for an hour after it rang; ask again — the bills and «Owed to
  // you» both — once the first one may ring. Never sooner than a moment, should
  // the phone's clock run ahead of the server's.
  useEffect(() => {
    const nextAt = Math.min(
      ...activeBills.map((bill) => (bill.collection?.next_reminder_at ? Date.parse(bill.collection.next_reminder_at) : Infinity)),
    );
    if (!Number.isFinite(nextAt)) return;
    const timer = setTimeout(() => {
      void loadActive();
      setOwedVersion((version) => version + 1);
    }, Math.max(MIN_RECHECK_MS, nextAt - Date.now() + 1000));
    return () => clearTimeout(timer);
  }, [activeBills, loadActive]);

  const selectTab = (tab: HomeTab) => {
    setSelectedTab(tab);
    track(AnalyticsEvent.HomeTabViewed, { tab });
  };

  const handleCreateBill = () => {
    // Bumping the key remounts the wizard, so it always opens on the first step
    // with an empty draft rather than resuming an abandoned one.
    setCreateSession((n) => n + 1);
    setShowCreateModal(true);
    track(AnalyticsEvent.BillCreateOpened, {});
  };

  const handleBillSubmit = async (data: BillCreateSubmit) => {
    if (!currentUser) {
      // `t` returns the key itself on a miss, so the old `|| '…'` fallback was
      // unreachable — and hardcoded English besides.
      showToast(t('bill.userNotSync'));
      return;
    }
    try {
      setLoading(true);
      const newBill = await createBill({
        title: data.title,
        total_sum: data.total_sum,
        owner_id: currentUser.id,
        payment_details: data.payment_details,
        expected_people: data.expected_people,
        // Whatever the wizard was showing when they filled it in.
        currency: data.currency,
        // Manual creation always includes the creator in the split.
        include_owner: true,
      });
      track(AnalyticsEvent.BillCreated, { source: data.voice ? 'voice' : 'manual', bill_id: newBill.id });
      if (!useTour.getState().active) useInvitePrompt.getState().offer(newBill.id);

      setShowCreateModal(false);
      router.push(`/bill/${newBill.id}${data.voice ? '?voice=1' : ''}`);
    } catch (error) {
      console.error('Failed to create bill:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteBill = async (billId: number) => {
    if (!currentUser) return;
    try {
      await deleteBill(billId, currentUser.id);
      track(AnalyticsEvent.BillDeleted, { bill_id: billId });
      setActiveBills((prev) => prev.filter((b) => b.id !== billId));
      archive.remove(billId);
      setOwedVersion((version) => version + 1);
    } catch (error) {
      console.error('Failed to delete bill:', error);
      showToast(t('common.error'));
    }
  };

  const handleRemind = async (bill: Bill) => {
    try {
      const { queued } = await sendReminders(bill.id);
      track(AnalyticsEvent.RemindersSent, { bill_id: bill.id, scope: 'bill', from: 'home', queued });
      showToast(
        queued > 0 ? t('bill.remindQueued', { count: String(queued) }) : t('bill.remindNobody'),
        queued > 0 ? 'success' : 'error',
      );
    } catch (error) {
      showToast(translateApiError(apiDetail(error), t));
    }
    await loadActive();
    setOwedVersion((version) => version + 1);
  };

  const handleMarkPaid = async (bill: Bill, paid: boolean) => {
    if (!currentUser || !bill.my_seat) return;
    try {
      await updatePaymentStatus(bill.id, bill.my_seat.id, paid, currentUser.id);
      track(AnalyticsEvent.PaymentMarked, { bill_id: bill.id, paid, by: 'self', from: 'home' });
    } catch (error) {
      showToast(translateApiError(apiDetail(error), t));
      throw error;
    }
  };

  const handleSettled = (billId: number) => {
    setActiveBills((prev) => prev.map((bill) => (
      bill.id === billId && bill.my_seat ? { ...bill, my_seat: { ...bill.my_seat, is_paid: true } } : bill
    )));
  };

  const emptyActive = (
    <motion.div
      className="flex flex-1 items-center justify-center py-2"
      initial="hidden"
      animate="visible"
      variants={EMPTY_STAGGER}
    >
      <div className="w-full rounded-[10px] border-[1.5px] border-dashed border-outline bg-surface px-6 py-7 text-center">
        <motion.div
          variants={EMPTY_ITEM}
          className="mx-auto mb-4 flex h-[54px] w-[54px] items-center justify-center rounded-[10px] border-[1.5px] border-outline text-muted-2"
        >
          <Receipt className="h-[26px] w-[26px]" />
        </motion.div>
        <motion.h3
          variants={EMPTY_ITEM}
          className="text-balance font-display text-[17px] font-bold text-foreground"
        >
          {t('home.noActiveBills')}
        </motion.h3>
        <motion.p
          variants={EMPTY_ITEM}
          className="mx-auto mt-[7px] max-w-xs text-pretty text-[13px] font-medium text-muted"
        >
          {t('home.createNewBillHint')}
        </motion.p>
        <motion.div variants={EMPTY_ITEM} className="mt-5 flex flex-col items-center gap-2">
          <Button type="button" onClick={handleCreateBill}>
            <Plus className="h-[18px] w-[18px]" />
            {t('bill.createTitle')}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => startTour('home')}>
            <GraduationCap className="h-4 w-4" />
            {t('home.howItWorks')}
          </Button>
        </motion.div>
      </div>
    </motion.div>
  );

  return (
    <div data-swipe-surface className="min-h-screen bg-background">
      {/* Header — ledger */}
      <AppHeader rowClassName="h-16 gap-2 px-[18px]">
          <div className="flex shrink-0 items-center gap-0.5 font-display text-lg font-bold tracking-[0.02em]">
            SPLIT<span className="text-accent">·</span>BILL
          </div>
          <ProfileChip className="ml-auto" />
          <ProButton />
          <SettingsMenu />
      </AppHeader>

      <main className="mx-auto max-w-[calc(42rem+var(--content-safe-left)+var(--content-safe-right))] pl-[calc(1rem+var(--content-safe-left))] pr-[calc(1rem+var(--content-safe-right))] pt-6 pb-[calc(95px+var(--content-safe-bottom))]">
        {loading ? (
          <div className="flex justify-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent" />
          </div>
        ) : (
          <>
            <HomeScreenBanner />
            {currentUser && (
              <OwedCard userId={currentUser.id} refreshKey={owedVersion} onReminded={() => void loadActive()} />
            )}

            <SwipeTabs
              label={t('home.billSections')}
              value={selectedTab}
              onChange={selectTab}
              tabs={[
                {
                  value: 'active',
                  label: t('home.tabActive'),
                  icon: Receipt,
                  badge: countBadge(activeBills.length),
                  content: (
                    <ActivePanel
                      bills={activeBills}
                      userId={currentUser?.id ?? 0}
                      empty={emptyActive}
                      onRemind={handleRemind}
                      onDelete={handleDeleteBill}
                      onMarkPaid={handleMarkPaid}
                      onSettled={handleSettled}
                    />
                  ),
                },
                {
                  value: 'archive',
                  label: t('home.tabArchive'),
                  icon: Archive,
                  badge: countBadge(archive.total),
                  content: <ArchivePanel archive={archive} userId={currentUser?.id ?? 0} onDelete={handleDeleteBill} />,
                },
                {
                  value: 'analytics',
                  label: t('home.tabAnalytics'),
                  icon: ChartColumn,
                  content: currentUser ? <AnalyticsPanel userId={currentUser.id} active={selectedTab === 'analytics'} /> : null,
                },
              ]}
            />
          </>
        )}
      </main>

      {/* The button that opened the sheet has nothing to do while it's open. */}
      <FloatingCreateButton
        onClick={handleCreateBill}
        ariaLabel={t('bill.createTitle')}
        show={!showCreateModal}
        tourAnchor={TourAnchor.CreateBill}
      />
      <CreateBillWizard
        key={createSession}
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSubmit={handleBillSubmit}
        existingBills={[...activeBills, ...archive.recent]}
      />

      {showLanguageStep && <LanguageStep onContinue={handleLanguageChosen} />}
    </div>
  );
}
