import { useRef, useState } from 'react';
import { BillDetail, BillStatus, User } from '@/types/api';
import { useRouter } from 'next/navigation';
import { LogOut } from 'lucide-react';
import BillOverview from './BillOverview';
import ParticipantCard from './ParticipantCard';
import ParticipantList from './ParticipantList';
import ParticipantItemsDialog from './ParticipantItemsDialog';
import InviteRow from './invite/InviteRow';
import MoveSeatDialog from './MoveSeatDialog';
import ItemsSection from './ItemsSection';
import BillDetailsTabs, { type BillTab } from './BillDetailsTabs';
import BillPaymentDock from './BillPaymentDock';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { updatePaymentStatus, deleteBillParticipant, getBill, claimSeat } from '@/lib/api/bills';
import { track, AnalyticsEvent } from '@/lib/analytics';
import Button from '@/components/ui/Button';
import Modal from '@/components/ui/Modal';
import { showToast } from '@/lib/toast';
import { translateApiError } from '@/lib/utils/apiError';
import ReceiptsSection from './receipts/ReceiptsSection';
import { useGuestTour } from '@/components/tour/useGuestTour';
import { canPickOwnItems, splitsByDishes } from '@/lib/utils/participants';

interface BillDetailsParticipantProps {
  bill: BillDetail;
  currentUser: User | null;
  setBill: (bill: BillDetail) => void;
}

export default function BillDetailsParticipant({
  bill,
  currentUser,
  setBill,
}: BillDetailsParticipantProps) {
  const { t } = useTranslation();
  const router = useRouter();
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);
  // The seat a confirmed move would land on; set when the server asks.
  const [movingToSeatId, setMovingToSeatId] = useState<number | null>(null);
  const [leaving, setLeaving] = useState(false);
  const [activeTab, setActiveTab] = useState<BillTab>('participants');
  const changeTab = (tab: BillTab) => {
    setActiveTab(tab);
    track(AnalyticsEvent.BillTabViewed, { bill_id: bill.id, tab, role: 'participant' });
  };
  const [pickingItems, setPickingItems] = useState(false);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const paymentBusyRef = useRef(false);
  // Find my participation record
  const myParticipation = bill.participants.find(
    (p) => p.user_id === currentUser?.id,
  );
  const isOpen = bill.status === BillStatus.OPEN;
  useGuestTour(bill, myParticipation);

  // Leave the bill: remove myself (frees a spot) and go back home. The bill
  // page would 403 on refresh once I'm no longer a participant, so navigate away.
  const handleLeave = async () => {
    if (!myParticipation || !currentUser || !isOpen) return;
    try {
      setLeaving(true);
      await deleteBillParticipant(bill.id, myParticipation.id, currentUser.id);
      track(AnalyticsEvent.BillLeft, { bill_id: bill.id });
      router.push('/');
    } catch (e: unknown) {
      console.error(e);
      setLeaving(false);
      setShowLeaveConfirm(false);
      showToast(
        translateApiError(
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail,
          t,
        ),
      );
    }
  };

  const handleTogglePaid = async () => {
    const canTogglePayment = isOpen
      || (bill.status === BillStatus.PAID && myParticipation?.is_paid === true);
    if (!myParticipation || !currentUser || !canTogglePayment || paymentBusyRef.current) return;

    paymentBusyRef.current = true;
    setPaymentBusy(true);
    try {
      const updated = await updatePaymentStatus(
        bill.id,
        myParticipation.id,
        !myParticipation.is_paid,
        currentUser.id,
      );
      setBill(updated);
      track(AnalyticsEvent.PaymentMarked, { bill_id: bill.id, paid: !myParticipation.is_paid, by: 'self', from: 'bill' });
    } catch (e: unknown) {
      console.error(e);
      showToast(
        translateApiError(
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail,
          t,
        ),
      );
    } finally {
      paymentBusyRef.current = false;
      setPaymentBusy(false);
    }
  };

  if (!myParticipation || !currentUser) {
    return (
      <div className="py-10 text-center">
        <p className="mb-4 text-muted">{t('bill.notParticipant')}</p>
        <Button>{t('bill.joinBill')}</Button>
      </div>
    );
  }

  // Sitting somewhere else: the seat you leave keeps its items, the one you take
  // hands you its own — which is the whole reason to move, and also why the
  // server will not do it until the question below has been answered.
  const handleTakeSeat = async (participantId: number, confirmed = false) => {
    if (!isOpen) return;
    try {
      setBill(await claimSeat(bill.id, participantId, currentUser.id, null, confirmed));
      track(AnalyticsEvent.SeatMoved, { bill_id: bill.id });
      setMovingToSeatId(null);
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (detail === 'SEAT_MOVE_CONFIRM') {
        setMovingToSeatId(participantId);
        return;
      }
      setMovingToSeatId(null);
      showToast(translateApiError(detail, t));
    }
  };

  const reloadBill = async () => {
    try {
      setBill(await getBill(bill.id, currentUser.id));
    } catch (e) {
      console.error(e);
    }
  };
  const receiptPanel = (
    <BillOverview bill={bill}>
      <ReceiptsSection
        bill={bill}
        currentUserId={currentUser.id}
        isCreator={false}
        currency={bill.currency ?? 'uzs'}
        onBillUpdate={setBill}
        onReload={reloadBill}
      />
      <ItemsSection
        billId={bill.id}
        items={bill.items}
        participants={bill.participants}
        currentUserId={currentUser.id}
        isCreator={false}
        isClosed={!isOpen}
        ownerId={bill.owner_id}
        requiresRecalculation={!splitsByDishes(bill)}
        currency={bill.currency ?? 'uzs'}
        onBillUpdate={setBill}
        receipts={bill.receipts}
      />
    </BillOverview>
  );

  const canPickItems = canPickOwnItems(bill, myParticipation);

  const participantsPanel = (
    <>
      {isOpen && <InviteRow bill={bill} />}
      <ParticipantList
        bill={bill}
        currentUserId={currentUser.id}
        renderRow={(participant) => (
          <ParticipantCard
            bill={bill}
            participant={participant}
            defaultExpanded={participant.id === myParticipation.id}
            onPickItems={participant.id === myParticipation.id && canPickItems ? () => setPickingItems(true) : undefined}
            onTakeSeat={participant.is_guest && isOpen ? () => void handleTakeSeat(participant.id) : undefined}
          />
        )}
      >
        {isOpen && (
          <button
            type="button"
            onClick={() => setShowLeaveConfirm(true)}
            className="mx-auto mt-6 flex min-h-11 items-center justify-center gap-1.5 rounded-md px-3 font-display text-[12px] font-bold text-muted transition-colors hover:text-danger active:text-danger"
          >
            <LogOut className="h-4 w-4" />
            {t('bill.leaveBill')}
          </button>
        )}
      </ParticipantList>
    </>
  );

  return (
    <div>
      <BillDetailsTabs
        value={activeTab}
        onChange={changeTab}
        participants={participantsPanel}
        receipt={receiptPanel}
      />

      <BillPaymentDock
        bill={bill}
        currentUser={currentUser}
        isCreator={false}
        loading={paymentBusy}
        onTogglePaid={
          isOpen || (bill.status === BillStatus.PAID && myParticipation.is_paid)
            ? handleTogglePaid
            : undefined
        }
        onSelectItems={canPickItems ? () => setPickingItems(true) : undefined}
      />

      <Modal
        isOpen={isOpen && showLeaveConfirm}
        onClose={() => !leaving && setShowLeaveConfirm(false)}
        title={t('bill.leaveBill')}
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-sm text-muted">{t('bill.leaveBillConfirm')}</p>
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={handleLeave}
              disabled={leaving}
              className="flex w-full items-center justify-center gap-2 rounded-lg border-[1.5px] border-outline bg-danger px-4 py-3 font-display text-[14px] font-bold text-danger-fg btn-hard disabled:opacity-50"
            >
              <LogOut className="h-[18px] w-[18px]" />
              {t('bill.leaveBill')}
            </button>
            <Button variant="ghost" onClick={() => setShowLeaveConfirm(false)} disabled={leaving}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* The same sheet the owner assigns with, pointed at the viewer's own seat. */}
      {pickingItems && canPickItems && (
        <ParticipantItemsDialog
          bill={bill}
          participant={myParticipation}
          currentUserId={currentUser.id}
          onBillUpdate={setBill}
          onClose={() => setPickingItems(false)}
        />
      )}

      <MoveSeatDialog
        isOpen={isOpen && movingToSeatId != null}
        onCancel={() => setMovingToSeatId(null)}
        onConfirm={() => void handleTakeSeat(movingToSeatId!, true)}
      />
    </div>
  );
}
