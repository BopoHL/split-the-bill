'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import dynamic from 'next/dynamic';
import { useParams, useRouter } from 'next/navigation';
import { useStore } from '@/lib/store/useStore';
import { getBill } from '@/lib/api/bills';
import { BillDetail } from '@/types/api';
import { Loader2, SearchX, Lock, Home } from 'lucide-react';
import BillDetailsCreator from '@/components/bill/BillDetailsCreator';
import BillDetailsParticipant from '@/components/bill/BillDetailsParticipant';
import BillTitleEditor from '@/components/bill/BillTitleEditor';
import EdgeSwipeBack from '@/components/layout/EdgeSwipeBack';
import SettingsMenu from '@/components/ui/SettingsMenu';
import ProfileChip from '@/components/profile/ProfileChip';
import ProButton from '@/components/pro/ProButton';
import ShareBillButton from '@/components/bill/invite/ShareBillButton';
import { showBackButton } from '@/lib/telegram/init';
import { useBillAutoRefresh } from '@/hooks/useBillAutoRefresh';
import { useBillEvents } from '@/hooks/useBillEvents';
import { useTranslation } from '@/lib/i18n/useTranslation';
import AppHeader from '@/components/layout/AppHeader';
import { showToast } from '@/lib/toast';
import { useTour } from '@/lib/tour/useTour';

// Dev-only widget for adding mock users to a bill without the invite
// link. The guard is a compile-time constant — the chunk is not emitted
// into production bundles.
const DevAddMockParticipants =
  process.env.NODE_ENV !== 'production'
    ? dynamic(() => import('@/components/dev/DevAddMockParticipants'), {
        ssr: false,
      })
    : null;

export default function BillPage() {
  const params = useParams();
  const router = useRouter();
  const { id } = params;
  const { currentUser } = useStore();
  const { t } = useTranslation();

  const [bill, setBillState] = useState<BillDetail | null>(null);
  const requestEpoch = useRef(0);
  const requestedBillId = useRef<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);

  // Mutation responses supersede any refresh that started before them.
  const setBill = useCallback((updated: BillDetail) => {
    if (updated.id !== requestedBillId.current) return;
    requestEpoch.current += 1;
    setBillState(updated);
    setError(false);
    setLoading(false);
  }, []);

  const goHome = useCallback(() => router.push('/'), [router]);

  useEffect(() => {
    // Releasing by identity, so an overlay opened on top keeps its own handler.
    return showBackButton(goHome);
  }, [goHome]);

  const fetchBill = useCallback(async (showLoading = false) => {
    if (!id || !currentUser) return;
    const epoch = ++requestEpoch.current;

    try {
      if (showLoading) setLoading(true);
      const billId = parseInt(Array.isArray(id) ? id[0] : id);
      if (isNaN(billId)) throw new Error('Invalid bill ID');
      requestedBillId.current = billId;

      const data = await getBill(billId, currentUser.id);
      if (epoch !== requestEpoch.current) return;
      setBillState(data);
      setError(false);
      setErrorStatus(null);
    } catch (err: unknown) {
      if (epoch !== requestEpoch.current) return;
      console.error('Error fetching bill:', err);
      const status =
        (err as { response?: { status?: number } })?.response?.status ?? null;
      // A background refresh that finds the bill gone, or the reader removed
      // from it, must not leave the old amounts on screen.
      if (showLoading || status === 403 || status === 404) {
        setErrorStatus(status);
        setError(true);
      }
    } finally {
      if (epoch === requestEpoch.current) setLoading(false);
    }
  }, [id, currentUser]);

  useEffect(() => {
    fetchBill(true);
    return () => { requestEpoch.current += 1; };
  }, [fetchBill]);

  // The owner can delete the bill while someone else has it open.
  const handleDeleted = useCallback(() => {
    showToast(t('bill.billDeleted'));
    router.push('/');
  }, [router, t]);

  // Subscribe to real-time events — until the bill is out of reach, when
  // following it only asks the server the same refused question every few seconds.
  const liveBillId = error ? undefined : bill?.id;
  useBillEvents(liveBillId, fetchBill, handleDeleted);
  useBillAutoRefresh(liveBillId, fetchBill);

  // The tour's bill reached some other way — a reload mid-tour, an old link —
  // is nothing to work with: the tour that gave it meaning is gone.
  const tourRunning = useTour((state) => state.active);
  const strayDemo = !!bill?.is_demo && !tourRunning;
  useEffect(() => {
    if (strayDemo) router.replace('/');
  }, [strayDemo, router]);

  if (loading || strayDemo) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center flex-col gap-4">
        <Loader2 className="w-7 h-7 text-accent animate-spin" />
        <p className="text-sm text-muted">{t('errors.loadingBill')}</p>
      </div>
    );
  }

  if (error || !bill) {
    const title =
      errorStatus === 403
        ? t('errors.forbiddenTitle')
        : errorStatus === 404
          ? t('errors.notFoundTitle')
          : t('errors.genericTitle');
    const text =
      errorStatus === 403
        ? t('errors.forbiddenText')
        : errorStatus === 404
          ? t('errors.billNotFoundText')
          : t('errors.genericText');
    const ErrorIcon = errorStatus === 403 ? Lock : SearchX;
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background p-6 text-center">
        <div className="mb-[18px] flex h-[58px] w-[58px] items-center justify-center rounded-[13px] border-[1.5px] border-outline text-muted-2">
          <ErrorIcon className="h-[27px] w-[27px]" />
        </div>
        <h3 className="font-display text-[19px] font-bold text-foreground">{title}</h3>
        <p className="mx-auto mt-2 max-w-[240px] text-[13px] font-medium leading-relaxed text-muted">
          {text}
        </p>
        <button
          onClick={() => router.push('/')}
          className="mt-[22px] inline-flex items-center gap-2 rounded-lg border-[1.5px] border-outline bg-accent px-[22px] py-3 font-display text-[14px] font-bold text-accent-fg btn-hard"
        >
          <Home className="h-[17px] w-[17px]" />
          {t('errors.goHome')}
        </button>
      </div>
    );
  }

  // Determine view mode
  if (!currentUser) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center flex-col gap-4">
        <Loader2 className="w-7 h-7 text-accent animate-spin" />
        <p className="text-sm text-muted">{t('common.loading')}</p>
      </div>
    );
  }

  const isCreator = currentUser.id === bill.owner_id;

  return (
    <div
      data-back-swipe-layer="page"
      data-swipe-surface
      className="relative z-[1] min-h-screen bg-background tracking-normal shadow-[-12px_0_28px_rgba(0,0,0,0.18)]"
    >
      <EdgeSwipeBack onBack={goHome} />
      {/* Header — topnav */}
      <AppHeader rowClassName="h-16 gap-1.5 px-3.5">
        <div className="min-w-0 flex-1">
          {/* Title is editable in the receipt block now — header shows it read-only. */}
          <BillTitleEditor
            bill={bill}
            currentUser={currentUser}
            setBill={setBill}
            canEdit={false}
          />
        </div>

        <ProfileChip />
        <ProButton />
        <SettingsMenu />
        <ShareBillButton bill={bill} />
      </AppHeader>

      <main className="mx-auto max-w-[calc(42rem+var(--content-safe-left)+var(--content-safe-right))] pb-6 pt-0 pl-[calc(1rem+var(--content-safe-left))] pr-[calc(1rem+var(--content-safe-right))]">
        {isCreator ? (
          <BillDetailsCreator
            key={bill.id}
            bill={bill}
            setBill={setBill}
            currentUser={currentUser}
          />
        ) : (
          <BillDetailsParticipant
            key={bill.id}
            bill={bill}
            currentUser={currentUser}
            setBill={setBill}
          />
        )}

        {DevAddMockParticipants && isCreator && (
          <DevAddMockParticipants
            billId={bill.id}
            existingUsernames={bill.participants
              .map((p) => p.username)
              .filter((u): u is string => !!u)}
            onAdded={() => fetchBill()}
          />
        )}
      </main>

    </div>
  );
}
