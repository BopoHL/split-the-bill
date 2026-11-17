'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AssignableUser, BillDetail, User, BillStatus } from '@/types/api';
import { formatCurrency } from '@/lib/utils/currency';
import Button from '@/components/ui/Button';
import Modal from '@/components/ui/Modal';
import {
  addBillItem,
  assignAmount,
  updatePaymentStatus,
  deleteBillParticipant,
  closeBill,
  reopenBill,
  updateBill,
  renameGuest,
  getBill,
  preparePersonalSeatInvite,
  assignSeatUser,
} from '@/lib/api/bills';
import { canShareMessage, shareMessage } from '@/lib/telegram/share';
import { billPositions, heldByPayment, positionsTotal, type BillPosition } from '@/lib/utils/billPositions';
import { useDishSelection } from '@/hooks/useDishSelection';
import { track, AnalyticsEvent } from '@/lib/analytics';
import BillOverview from './BillOverview';
import ParticipantCard from './ParticipantCard';
import InviteRow from './invite/InviteRow';
import InvitePrompt from './invite/InvitePrompt';
import AssignUserPicker from './AssignUserPicker';
import ItemsSection from './ItemsSection';
import BillDetailsTabs, { type BillTab } from './BillDetailsTabs';
import BillPaymentDock from './BillPaymentDock';
import DishSelectionBar from './DishSelectionBar';
import ItemAssignmentDialog from './ItemAssignmentDialog';
import ParticipantItemsDialog from './ParticipantItemsDialog';
import ParticipantList from './ParticipantList';
import HeadcountEditor from './HeadcountEditor';
import RemindEveryoneRow from './RemindEveryoneRow';
import { sendReminders } from '@/lib/api/reminders';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { translateApiError } from '@/lib/utils/apiError';
import ReceiptsSection from './receipts/ReceiptsSection';
import VoiceSheet, { VoiceButton } from './VoiceSheet';
import DishTable from './DishTable';
import { TourAnchor } from '@/lib/tour/anchors';
import { splitsByDishes } from '@/lib/utils/participants';

interface BillDetailsCreatorProps {
  bill: BillDetail;
  setBill: (bill: BillDetail) => void;
  currentUser: User | null;
}

export default function BillDetailsCreator({ bill, setBill, currentUser }: BillDetailsCreatorProps) {
  const { t, language } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  // A bill made to be said out loud opens on its receipt with the sheet up.
  const wantsVoice = searchParams.get('voice') === '1';
  const [activeTab, setActiveTab] = useState<BillTab>(() =>
    searchParams.get('scan') === '1' || wantsVoice ? 'receipt' : 'participants',
  );
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [tableOpen, setTableOpen] = useState(false);
  const openVoice = (from: 'bill' | 'new_bill') => {
    setVoiceOpen(true);
    track(AnalyticsEvent.VoiceInputOpened, { bill_id: bill.id, from });
  };
  const [isAdding, setIsAdding] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);
  const [removingParticipantId, setRemovingParticipantId] = useState<number | null>(null);
  const [invitingParticipantId, setInvitingParticipantId] = useState<number | null>(null);
  const [assigningParticipantId, setAssigningParticipantId] = useState<number | null>(null);
  const [assigningItemsParticipantId, setAssigningItemsParticipantId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const isOpen = bill.status === BillStatus.OPEN;

  useEffect(() => {
    if (!wantsVoice || !isOpen) return;
    openVoice('new_bill');
    // Consumed — otherwise going back to the bill opens the sheet again.
    router.replace(`/bill/${bill.id}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantsVoice, isOpen, bill.id, router]);
  const requiresRecalculation = !splitsByDishes(bill);
  const currency = bill.currency ?? 'uzs';

  // Dishes picked on the receipt to hand out together. The dock carries the
  // pick, and the pick ends with the hand-out or with leaving the receipt.
  const selection = useDishSelection();
  const [assigningPicked, setAssigningPicked] = useState<BillPosition[] | null>(null);
  const picking = isOpen && selection.active;
  const positions = billPositions(bill.items, bill.participants, bill.currency);
  // A dish someone has paid for since it was picked drops out, as it does on
  // the receipt: kept, it froze the whole hand-out.
  const picked = positions.filter((position) => selection.keys.has(position.key)
    && !heldByPayment(position.participantIds, bill.participants, bill.owner_id));
  const pickedSum = positionsTotal(picked);
  const freeLeft = positions.filter((position) =>
    !position.item.is_shared_globally && position.participantIds.length === 0 && !selection.keys.has(position.key));
  const changeTab = (tab: BillTab) => {
    setActiveTab(tab);
    track(AnalyticsEvent.BillTabViewed, { bill_id: bill.id, tab, role: 'owner' });
    if (tab !== 'receipt') selection.stop();
  };

  // Refetch after the mutation so receipt totals and allocations come from the
  // server response.
  const handleAddItem = async (name: string, price: number, count: number) => {
    if (!currentUser || !name.trim() || !Number.isFinite(price) || !Number.isInteger(count) || count < 1) return;
    try {
      setLoading(true);
      await addBillItem(bill.id, { name, price, count });
      // Added: a reload that fails must not leave the form open to add it twice.
      track(AnalyticsEvent.ItemsAdded, { bill_id: bill.id, count: 1 });
      setIsAdding(false);
      await reloadBill();
    } catch (e) {
      console.error(e);
      showToast(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const assigningItemsParticipant = assigningItemsParticipantId == null
    ? undefined
    : bill.participants.find((participant) => participant.id === assigningItemsParticipantId);

  const handleTogglePaymentStatus = async (participantId: number, currentPaid: boolean) => {
    if (!currentUser) return;

    try {
      setLoading(true);
      const updated = await updatePaymentStatus(bill.id, participantId, !currentPaid, currentUser.id);
      setBill(updated);
      track(AnalyticsEvent.PaymentMarked, { bill_id: bill.id, paid: !currentPaid, by: 'owner', from: 'bill' });
    } catch (e: unknown) {
      console.error(e);
      showToast(translateApiError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail, t));
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteParticipant = async (participantId: number) => {
    if (!currentUser) return;
    setRemovingParticipantId(null);

    try {
      setLoading(true);
      const updatedBill = await deleteBillParticipant(bill.id, participantId, currentUser.id);
      setBill(updatedBill);
      track(AnalyticsEvent.ParticipantRemoved, { bill_id: bill.id });
    } catch (e) {
      console.error(e);
      showToast(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const handleCloseBill = () => {
    if (!currentUser) return;
    // A bill can't be closed with an unallocated remainder — make the owner
    // choose how to distribute it first (STB-93). No remainder → close directly.
    if (bill.unallocated_sum > 0) {
      setShowCloseConfirm(true);
      return;
    }
    void closeNow();
  };

  const closeNow = async () => {
    if (!currentUser) return;
    try {
      setLoading(true);
      await closeBill(bill.id, currentUser.id);
      track(AnalyticsEvent.BillClosed, { bill_id: bill.id, remainder: 'none' });
      setShowCloseConfirm(false);
      // A closed bill has nothing left to do on this screen — go back to the list.
      router.push('/');
    } catch (e) {
      console.error(e);
      showToast(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  // Hand what nobody took to me, or to everyone in the bill, and close — one
  // request, so a failed close leaves nobody's amount changed.
  const doCloseBill = async (mode: 'me' | 'all') => {
    if (!currentUser) return;
    try {
      setLoading(true);
      await closeBill(bill.id, currentUser.id, mode);
      track(AnalyticsEvent.BillClosed, { bill_id: bill.id, remainder: mode });
      setShowCloseConfirm(false);
      // A closed bill has nothing left to do on this screen — go back to the list.
      router.push('/');
    } catch (e) {
      console.error(e);
      showToast(translateApiError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail, t));
    } finally {
      setLoading(false);
    }
  };

  const reloadBill = async () => {
    if (!currentUser) return;
    try {
      setBill(await getBill(bill.id, currentUser.id));
    } catch (e) {
      console.error(e);
    }
  };

  /** One seat, or everyone who still owes when none is named. The bill comes
   *  back with the reminders pending; how they went arrives by itself. */
  const handleRemind = async (participantId?: number) => {
    try {
      const { queued } = await sendReminders(bill.id, participantId);
      track(AnalyticsEvent.RemindersSent, { bill_id: bill.id, scope: participantId == null ? 'bill' : 'seat', from: 'bill', queued });
      showToast(queued > 0 ? t('bill.remindQueued', { count: String(queued) }) : t('bill.remindNobody'), queued > 0 ? 'success' : 'error');
    } catch (e: unknown) {
      console.error(e);
      showToast(translateApiError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail, t));
    }
    await reloadBill();
  };

  const handleRenameGuest = async (participantId: number, name: string) => {
    if (!currentUser) return;
    try {
      await renameGuest(bill.id, participantId, currentUser.id, name || null);
      track(AnalyticsEvent.GuestRenamed, { bill_id: bill.id });
      setBill(await getBill(bill.id, currentUser.id));
    } catch (e) {
      console.error(e);
      showToast(t('common.error'));
      throw e;
    }
  };

  /** The «or hand it over yourself» route out of the add-person sheet. The
   *  sheet stays open unless the share sheet actually took over: a person who
   *  got a toast instead still has the list in front of them. */
  const handleSendPersonalInvite = async () => {
    if (assigningParticipantId == null) return;
    if (await handleInviteGuest(assigningParticipantId)) {
      setAssigningParticipantId(null);
    }
  };

  /** Hand the invite to Telegram's share sheet. Resolves true once the sheet
   *  has been opened. */
  const handleInviteGuest = async (participantId: number): Promise<boolean> => {
    if (!currentUser || invitingParticipantId != null) return false;
    if (!canShareMessage()) {
      showToast(t('bill.personalInviteUnsupported'));
      return false;
    }

    try {
      setInvitingParticipantId(participantId);
      const preparedId = await preparePersonalSeatInvite(bill.id, participantId, language);
      if (!shareMessage(preparedId)) {
        showToast(t('bill.personalInviteUnsupported'));
        return false;
      }
      track(AnalyticsEvent.ShareInvite, { method: 'message', channel: 'seat', bill_id: bill.id });
      return true;
    } catch (e: unknown) {
      console.error(e);
      showToast(
        translateApiError(
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail,
          t,
        ),
      );
      return false;
    } finally {
      setInvitingParticipantId(null);
    }
  };

  const handleAssignUser = async (user: AssignableUser) => {
    if (!currentUser || assigningParticipantId == null) return;
    try {
      setBill(await assignSeatUser(bill.id, assigningParticipantId, user.user_id, language));
      track(AnalyticsEvent.SeatUserAssigned, { bill_id: bill.id });
      setAssigningParticipantId(null);
      showToast(t('bill.assignUserDone'));
    } catch (e: unknown) {
      console.error(e);
      showToast(
        translateApiError(
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail,
          t,
        ),
      );
    }
  };

  const handleReopenBill = async () => {
    if (!currentUser) return;
    try {
      setLoading(true);
      const updatedBill = await reopenBill(bill.id, currentUser.id);
      setBill(updatedBill);
      track(AnalyticsEvent.BillReopened, { bill_id: bill.id });
    } catch (e) {
      console.error(e);
      showToast(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const handleAssignAmount = async (participantId: number, amount: number) => {
    try {
      setLoading(true);
      // The endpoint returns the full recomputed bill — no client-side math.
      const updated = await assignAmount(bill.id, participantId, amount);
      setBill(updated);
      track(AnalyticsEvent.AmountAssigned, { bill_id: bill.id });
    } catch (e: unknown) {
      console.error(e);
      // Surface the backend message (e.g. "Amount exceeds unallocated sum.
      // Max available: …") instead of failing silently / generically.
      showToast(translateApiError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail, t));
    } finally {
      setLoading(false);
    }
  };

  const handleUpdatePaymentDetails = async (newDetails: string) => {
    if (!currentUser) return;
    try {
      setLoading(true);
      const updatedBill = await updateBill(bill.id, {
        payment_details: newDetails || null,
        user_id: currentUser.id
      });
      setBill(updatedBill);
      track(AnalyticsEvent.BillEdited, { bill_id: bill.id, field: 'payment_details' });
    } catch (e) {
      console.error(e);
      showToast(t('common.error'));
      throw e;
    } finally {
      setLoading(false);
    }
  };

  // Rename the bill from the receipt title (owner of an open bill).
  const handleUpdateTitle = async (newTitle: string) => {
    if (!currentUser) return;
    const updatedBill = await updateBill(bill.id, {
      title: newTitle || null,
      user_id: currentUser.id,
    });
    setBill(updatedBill);
    track(AnalyticsEvent.BillEdited, { bill_id: bill.id, field: 'title' });
  };

  return (
    <div>
      <BillDetailsTabs
        value={activeTab}
        onChange={changeTab}
        receipt={(
          <BillOverview
            bill={bill}
            onUpdateTitle={handleUpdateTitle}
            canEditTitle={currentUser?.id === bill.owner_id && bill.status === BillStatus.OPEN}
            onPlaceChange={(place) => setBill({ ...bill, place })}
          >
            <ReceiptsSection
              bill={bill}
              currentUserId={currentUser?.id}
              isCreator
              currency={bill.currency ?? 'uzs'}
              onBillUpdate={setBill}
              onReload={reloadBill}
            />
            <ItemsSection
              billId={bill.id}
              items={bill.items}
              participants={bill.participants}
              currentUserId={currentUser?.id ?? 0}
              isCreator={true}
              isClosed={bill.status !== BillStatus.OPEN}
              ownerId={bill.owner_id}
              requiresRecalculation={requiresRecalculation}
              currency={currency}
              isAdding={isAdding}
              onAddItem={handleAddItem}
              onCancelAdd={() => setIsAdding(false)}
              onStartAdd={() => setIsAdding(true)}
              onTable={bill.participants.length > 1 ? () => {
                setTableOpen(true);
                track(AnalyticsEvent.DishTableOpened, { bill_id: bill.id });
              } : undefined}
              onBillUpdate={setBill}
              receipts={bill.receipts}
              selection={selection}
            />
          </BillOverview>
        )}
        participants={(
          <>
            {isOpen && <InviteRow bill={bill} />}
            {isOpen && <InvitePrompt key={bill.id} bill={bill} />}
            {isOpen && <RemindEveryoneRow bill={bill} onRemindEveryone={() => handleRemind()} />}
            <ParticipantList
              bill={bill}
              currentUserId={currentUser?.id}
              headcount={isOpen && currentUser ? (
                <HeadcountEditor bill={bill} userId={currentUser.id} onBillUpdate={setBill} />
              ) : undefined}
              renderRow={(p) => (
                <ParticipantCard
                  bill={bill}
                  participant={p}
                  defaultExpanded={p.user_id === currentUser?.id}
                  onAssignItems={isOpen && currentUser ? () => setAssigningItemsParticipantId(p.id) : undefined}
                  onAssignAmount={bill.items.length === 0 && bill.total_sum > 0 ? handleAssignAmount : undefined}
                  onTogglePayment={handleTogglePaymentStatus}
                  onDelete={setRemovingParticipantId}
                  onRenameGuest={handleRenameGuest}
                  onAddPerson={isOpen && p.is_guest && p.user_id == null ? setAssigningParticipantId : undefined}
                  onRemind={isOpen ? handleRemind : undefined}
                />
              )}
            />
          </>
        )}
      />

      <BillPaymentDock
        bill={bill}
        currentUser={currentUser}
        isCreator
        loading={loading}
        onUpdatePaymentDetails={handleUpdatePaymentDetails}
        onCloseBill={handleCloseBill}
        onReopenBill={handleReopenBill}
        fab={isOpen && !picking ? <VoiceButton onPress={() => openVoice('bill')} /> : undefined}
        takeover={picking ? (
          <DishSelectionBar
            count={picked.length}
            amount={pickedSum}
            currency={currency}
            freeLeft={freeLeft.length}
            onPickFree={() => selection.add(freeLeft.map((position) => position.key))}
            onClear={selection.clear}
            onAssign={() => setAssigningPicked(picked)}
          />
        ) : undefined}
      />

      {assigningPicked && isOpen && (
        <ItemAssignmentDialog
          key={assigningPicked.map((position) => position.key).join(',')}
          positions={assigningPicked}
          participants={bill.participants}
          billId={bill.id}
          currentUserId={currentUser?.id ?? 0}
          ownerId={bill.owner_id}
          requiresRecalculation={requiresRecalculation}
          currency={currency}
          onBillUpdate={(updated) => {
            setBill(updated);
            selection.stop();
          }}
          onClose={() => setAssigningPicked(null)}
        />
      )}

      <AssignUserPicker
        billId={bill.id}
        isOpen={assigningParticipantId != null}
        onClose={() => setAssigningParticipantId(null)}
        onPick={handleAssignUser}
        onSendPersonalInvite={handleSendPersonalInvite}
      />

      {assigningItemsParticipant && currentUser && (
        <ParticipantItemsDialog
          key={assigningItemsParticipant.id}
          bill={bill}
          participant={assigningItemsParticipant}
          currentUserId={currentUser.id}
          onBillUpdate={setBill}
          onClose={() => setAssigningItemsParticipantId(null)}
        />
      )}

      {/* Modals */}
      <Modal
        isOpen={showCloseConfirm}
        onClose={() => setShowCloseConfirm(false)}
        title={t('bill.unallocatedOnCloseTitle')}
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-sm text-muted">
            {t('bill.unallocatedOnCloseText', {
              amount: formatCurrency(bill.unallocated_sum, bill.currency ?? 'uzs'),
            })}
          </p>
          <div className="flex flex-col gap-2">
            <Button onClick={() => doCloseBill('me')} disabled={loading}>
              {t('bill.assignRemainderToMe')}
            </Button>
            <Button onClick={() => doCloseBill('all')} disabled={loading} data-tour={TourAnchor.SplitRemainder}>
              {t('bill.splitRemainderAmongAll')}
            </Button>
            <Button variant="ghost" onClick={() => setShowCloseConfirm(false)} disabled={loading}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={removingParticipantId != null}
        onClose={() => setRemovingParticipantId(null)}
        title={t('bill.removeParticipant')}
        size="sm"
      >
        <p className="text-[15px] leading-snug text-foreground">
          {t('bill.removeParticipantAlert')}
        </p>
        <div className="mt-5 flex gap-2.5">
          <Button variant="primary" className="flex-1" onClick={() => setRemovingParticipantId(null)}>
            {t('common.back')}
          </Button>
          <Button
            variant="danger"
            className="flex-1 border-[1.5px] border-danger"
            isLoading={loading}
            onClick={() => {
              if (removingParticipantId != null) {
                void handleDeleteParticipant(removingParticipantId);
              }
            }}
          >
            {t('common.delete')}
          </Button>
        </div>
      </Modal>

      {tableOpen && isOpen && currentUser && (
        <DishTable bill={bill} currentUserId={currentUser.id} onBillUpdate={setBill} onClose={() => setTableOpen(false)} />
      )}
      <VoiceSheet billId={bill.id} isOpen={voiceOpen} onClose={() => setVoiceOpen(false)} onBillUpdate={setBill} />
    </div>
  );
}
