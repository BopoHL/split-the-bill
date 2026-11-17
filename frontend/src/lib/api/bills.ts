import apiClient from './client';
import type {
  AssignableUser,
  Bill,
  BillCounts,
  BillCreate,
  BillDetail,
  BillItem,
  BillItemCreate,
  BillItemPositionParams,
  BillParticipant,
  BillUpdate,
  BillItemUpdate,
  BillSeats,
  ReceiptDeleteImpact,
} from '@/types/api';
import type { Language } from '@/lib/i18n/translations';

/**
 * Create a new bill
 */
export async function createBill(billData: BillCreate): Promise<Bill> {
  const response = await apiClient.post<Bill>('/bills/', billData);
  return response.data;
}

export interface VoiceBillResult {
  /** What the server heard, or the text as it was typed. */
  heard: string;
  added: number;
  assigned: number;
  /** Lines left as they were: changing them would move a share already paid. */
  held: string[];
  /** Names said that no seat could be found or laid for. */
  unseated: string[];
  bill: BillDetail;
}

/** The words of a recording, before anything is done with them. Pro only; the owner's. */
export async function hearBill(billId: number, recording: Blob): Promise<string> {
  const formData = new FormData();
  formData.append('audio', recording, 'voice');
  const response = await apiClient.post<{ heard: string }>(`/bills/${billId}/voice/hear`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    // The server gives OpenAI 40 s; the upload comes on top.
    timeout: 60000,
  });
  return response.data.heard;
}

/**
 * Tell the bill what was ordered and who had it — heard from a recording, or
 * typed. Pro only; the owner's.
 */
export async function tellBill(billId: number, words: string): Promise<VoiceBillResult> {
  const formData = new FormData();
  formData.append('text', words);
  const response = await apiClient.post<VoiceBillResult>(`/bills/${billId}/voice`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  });
  return response.data;
}

/**
 * Get bill details with items and participants
 */
export async function getBill(
  billId: number,
  userId: number,
): Promise<BillDetail> {
  const response = await apiClient.get<BillDetail>(`/bills/${billId}`, {
    params: { user_id: userId },
  });
  return response.data;
}

/**
 * Delete a bill (owner only).
 */
export async function deleteBill(billId: number, userId: number): Promise<void> {
  await apiClient.delete(`/bills/${billId}`, { params: { user_id: userId } });
}

/**
 * Update a bill (e.g. payment details)
 */
export async function updateBill(billId: number, updateData: BillUpdate): Promise<BillDetail> {
  const response = await apiClient.patch<BillDetail>(`/bills/${billId}`, updateData);
  return response.data;
}

/**
 * Add an item to a bill
 */
export async function addBillItem(
  billId: number,
  itemData: BillItemCreate
): Promise<BillItem> {
  const response = await apiClient.post<BillItem>(
    `/bills/${billId}/items`,
    itemData
  );
  return response.data;
}

/**
 * Edit an item (name / price / count / shared flag)
 */
export async function updateBillItem(
  billId: number,
  itemId: number,
  data: BillItemUpdate,
  position?: BillItemPositionParams,
): Promise<BillItem> {
  const response = await apiClient.patch<BillItem>(
    `/bills/${billId}/items/${itemId}`,
    data,
    position ? { params: position } : undefined,
  );
  return response.data;
}

/**
 * Delete an item from a bill, every dish of it
 */
export async function deleteBillItem(billId: number, itemId: number): Promise<void> {
  await apiClient.delete(`/bills/${billId}/items/${itemId}`);
}

/**
 * Assign or unassign a SEAT to a specific item. Seats, not accounts: an
 * unclaimed guest can be given dishes before anyone opens the invite.
 */
export interface BillItemAssignOp {
  item_id: number;
  participant_id: number;
  is_assigned: boolean;
  portion_index?: number;
  expected_count?: number;
}

export interface BillItemSharedOp {
  item_id: number;
  is_shared_globally: boolean;
}

/**
 * Apply a whole multi-select of assign/unassign (and shared-flag) operations in
 * ONE request and get the updated bill back — replaces firing N single-assign
 * calls, which triggered N SSE refetches that raced and dropped portions on iOS.
 */
export async function assignBillItemsBatch(
  billId: number,
  requesterId: number,
  ops: BillItemAssignOp[],
  shared: BillItemSharedOp[] = [],
): Promise<BillDetail> {
  const response = await apiClient.post<BillDetail>(
    `/bills/${billId}/items/assign-batch`,
    { ops, shared },
    { params: { requester_id: requesterId } },
  );
  return response.data;
}


export async function updatePaymentStatus(
  billId: number,
  participantId: number,
  isPaid: boolean,
  userId: number
): Promise<BillDetail> {
  const response = await apiClient.post<BillDetail>(`/bills/${billId}/participants/${participantId}/payment`, {
    is_paid: isPaid,
    user_id: userId
  });
  return response.data;
}

/**
 * Get bills for a user with pagination.
 *
 * `status`:
 *  - `'active'` — non-closed bills (open/paid)
 *  - `'closed'` — history (closed bills)
 *  - omitted    — all bills, newest first (legacy callers)
 */
export type BillStatusFilter = 'active' | 'closed';

export type BillRoleFilter = 'owner' | 'participant';

export interface BillSearch {
  query?: string;
  role?: BillRoleFilter;
}

/** The person's bills, newest first, from `offset` — how many are shown already. */
export async function getUserBills(
  userId: number,
  offset: number = 0,
  limit: number = 10,
  status?: BillStatusFilter,
  search: BillSearch = {},
): Promise<Bill[]> {
  const response = await apiClient.get<Bill[]>(`/users/${userId}/bills`, {
    params: { offset, limit, status, q: search.query || undefined, role: search.role },
  });
  return response.data;
}

/** How many bills a search finds — in all, owned, and only joined. */
export async function getBillCounts(userId: number, status: BillStatusFilter, query?: string): Promise<BillCounts> {
  const response = await apiClient.get<BillCounts>(`/users/${userId}/bills/counts`, {
    params: { status, q: query || undefined },
  });
  return response.data;
}

export async function closeBill(
  billId: number,
  userId: number,
  /** Hand what nobody took to me or to every seat first, in the same request. */
  remainder?: 'me' | 'all',
): Promise<BillDetail> {
  const response = await apiClient.post<BillDetail>(`/bills/${billId}/close`, {
    user_id: userId,
    remainder: remainder ?? null,
  });
  return response.data;
}

/**
 * Reopen a closed bill (owner only): CLOSED → OPEN.
 */
export async function reopenBill(billId: number, userId: number): Promise<BillDetail> {
  const response = await apiClient.post<BillDetail>(`/bills/${billId}/reopen`, {
    user_id: userId,
  });
  return response.data;
}



/**
 * Direct Mini App link for a bill's public token — the invite as it existed
 * before invites were minted. Still honoured by the app, and used as the
 * fallback when minting a code fails, but it carries no attribution.
 */
export function inviteDeepLink(token: string): string {
  const botUsername = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME ?? '';
  const cleanUsername = botUsername.startsWith('@') ? botUsername.slice(1) : botUsername;
  return `https://t.me/${cleanUsername}/app?startapp=join_${token}`;
}

/**
 * Ask the backend for the bill's chat post and return its prepared message id
 * for WebApp.shareMessage. The server writes the post — the ticket picture
 * above who owes what — in the sharer's language, and keeps it current.
 */
export async function prepareShareMessage(billId: number, lang: Language): Promise<string> {
  const response = await apiClient.post<{ prepared_message_id: string }>(
    `/bills/${billId}/prepare-share`,
    { lang },
  );
  return response.data.prepared_message_id;
}

/**
 * Prepare a one-seat invite. The resulting message can be sent only to a
 * private Telegram chat and its CTA claims this exact guest seat.
 */
export async function preparePersonalSeatInvite(
  billId: number,
  participantId: number,
  lang?: string,
): Promise<string> {
  const response = await apiClient.post<{ prepared_message_id: string }>(
    `/bills/${billId}/seats/${participantId}/prepare-invite`,
    { lang: lang ?? null },
  );
  return response.data.prepared_message_id;
}

/**
 * People the owner may seat: those they have shared a bill with or brought into
 * the app. With `q`, a username lookup instead. Owner only.
 */
export async function getAssignableUsers(
  billId: number,
  q?: string,
): Promise<AssignableUser[]> {
  const response = await apiClient.get<AssignableUser[]>(
    `/bills/${billId}/assignable-users`,
    { params: q ? { q } : undefined },
  );
  return response.data;
}

/**
 * Seat a known person and have the bot send them the invite. The seat is left
 * free if the bot cannot write to them, so a rejected call changes nothing.
 */
export async function assignSeatUser(
  billId: number,
  participantId: number,
  targetUserId: number,
  lang?: string,
): Promise<BillDetail> {
  const response = await apiClient.post<BillDetail>(
    `/bills/${billId}/seats/${participantId}/assign`,
    { target_user_id: targetUserId, lang: lang ?? null },
  );
  return response.data;
}

/**
 * After joining via an invite link and granting write access, ask the bot to DM
 * the new participant so it lands in their chat list. Best-effort.
 */
export async function joinWelcome(billId: number, lang?: string): Promise<void> {
  await apiClient.post(`/bills/${billId}/join-welcome`, { lang: lang ?? null });
}

/**
 * The owner seats someone by hand (first free seat, or a new one).
 */
export async function addBillParticipant(billId: number, userId: number): Promise<BillParticipant[]> {
  const response = await apiClient.post<BillParticipant[]>(`/bills/${billId}/participants`, {
    user_id: userId
  });
  return response.data;
}

/**
 * Join a bill via its unguessable public token (invite-link flow).
 * The returned participant carries the bill_id to navigate to.
 */
export async function joinByToken(
  token: string,
  userId: number,
  inviteCode?: string | null,
): Promise<BillParticipant> {
  const response = await apiClient.post<BillParticipant>(`/bills/join-by-token`, {
    token,
    user_id: userId,
    invite_code: inviteCode ?? null,
  });
  return response.data;
}
/**
 * Assign a specific amount to a participant
 */
export async function assignAmount(
  billId: number,
  participantId: number,
  allocatedAmount: number
): Promise<BillDetail> {
  const response = await apiClient.post<BillDetail>(
    `/bills/${billId}/assign-amount`,
    {
      participant_id: participantId,
      allocated_amount: allocatedAmount,
    }
  );
  return response.data;
}
/**
 * Delete a participant from a bill
 */
export async function deleteBillParticipant(
  billId: number,
  participantId: number,
  userId: number
): Promise<BillDetail> {
  const response = await apiClient.delete<BillDetail>(
    `/bills/${billId}/participants/${participantId}`,
    { data: { user_id: userId } }
  );
  return response.data;
}
/**
 * Rate ONE receipt's scan 1–5 (owner only).
 *
 * Per receipt rather than per bill: a bill can hold several scanned with very
 * different results, so a single number said nothing.
 */
export async function rateReceipt(
  billId: number,
  taskId: number,
  rating: number,
  userId: number,
): Promise<void> {
  await apiClient.post(`/bills/${billId}/receipts/${taskId}/feedback`, {
    rating,
    user_id: userId,
  });
}

/** Seats behind an invite link — readable before you're a participant. */
export async function getSeatsByToken(token: string, userId?: number): Promise<BillSeats> {
  const response = await apiClient.get<BillSeats>(`/bills/public/${token}/seats`, {
    params: userId != null ? { user_id: userId } : undefined,
  });
  return response.data;
}

/**
 * Sit down at a seat, or move to a different one.
 *
 * Moving is refused with SEAT_MOVE_CONFIRM until `confirmMove` is set: the seat
 * being left keeps its dishes, so a move has to be a decision rather than the
 * side effect of tapping a link.
 *
 * Someone not yet in the bill needs `token` (the invite link's) or an invite
 * code: seat ids are sequential, so they alone let nobody in.
 */
export async function claimSeat(
  billId: number,
  participantId: number,
  userId: number,
  inviteCode?: string | null,
  confirmMove = false,
  token?: string | null,
): Promise<BillDetail> {
  const response = await apiClient.post<BillDetail>(
    `/bills/${billId}/seats/${participantId}/claim`,
    {
      user_id: userId,
      invite_code: inviteCode ?? null,
      confirm_move: confirmMove,
      token: token ?? null,
    },
  );
  return response.data;
}


/** Label an unclaimed guest seat. Blank resets it to the default «Guest N». */
export async function renameGuest(
  billId: number,
  participantId: number,
  userId: number,
  guestName: string | null,
): Promise<BillParticipant> {
  const response = await apiClient.patch<BillParticipant>(
    `/bills/${billId}/participants/${participantId}`,
    { user_id: userId, guest_name: guestName },
  );
  return response.data;
}

/** What removing a receipt would take with it — quoted in the confirmation. */
export async function getReceiptDeleteImpact(
  billId: number,
  taskId: number,
  userId: number,
): Promise<ReceiptDeleteImpact> {
  const response = await apiClient.get<ReceiptDeleteImpact>(
    `/bills/${billId}/receipts/${taskId}/impact`,
    { params: { user_id: userId } },
  );
  return response.data;
}

/** Remove a receipt; `keepItems` detaches its lines instead of deleting them. */
export async function deleteReceipt(
  billId: number,
  taskId: number,
  userId: number,
  keepItems: boolean,
): Promise<BillDetail> {
  const response = await apiClient.delete<BillDetail>(
    `/bills/${billId}/receipts/${taskId}`,
    { params: { user_id: userId, items: keepItems ? 'keep' : 'delete' } },
  );
  return response.data;
}

/** API path of one receipt's photo. Served only to bill members, so it is
 *  fetched through the API client rather than dropped into <img src>. */
export function receiptImagePath(billId: number, taskId: number): string {
  return `/bills/${billId}/receipts/${taskId}/image`;
}
