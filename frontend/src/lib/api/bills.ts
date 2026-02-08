import apiClient from './client';
import type {
  Bill,
  BillCreate,
  BillDetail,
  BillItem,
  BillItemCreate,
  BillParticipant,
  BillParticipantCreate,
} from '@/types/api';

/**
 * Create a new bill
 */
export async function createBill(billData: BillCreate): Promise<Bill> {
  const response = await apiClient.post<Bill>('/bills/', billData);
  return response.data;
}

/**
 * Get bill details with items and participants
 */
export async function getBill(billId: number): Promise<BillDetail> {
  const response = await apiClient.get<BillDetail>(`/bills/${billId}`);
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
 * Delete an item from a bill
 */
export async function deleteBillItem(
  billId: number,
  itemId: number
): Promise<void> {
  await apiClient.delete(`/bills/${billId}/items/${itemId}`);
}

/**
 * Add a participant to a bill
 */
export async function addBillParticipant(
  billId: number,
  participantData: BillParticipantCreate
): Promise<BillParticipant[]> {
  const response = await apiClient.post<BillParticipant[]>(
    `/bills/${billId}/participants`,
    participantData
  );
  return response.data;
}

export async function markAsPaid(
  billId: number,
  participantId: number
): Promise<void> {
  await apiClient.patch(`/bills/${billId}/participants/${participantId}/paid`);
}

export async function updatePaymentStatus(
  billId: number,
  participantId: number,
  isPaid: boolean,
  userId: number
): Promise<BillParticipant> {
  const response = await apiClient.post<BillParticipant>(`/bills/${billId}/participants/${participantId}/payment`, {
    is_paid: isPaid,
    user_id: userId
  });
  return response.data;
}

/**
 * Get all bills for a user with pagination
 */
export async function getUserBills(
  userId: number,
  page: number = 1,
  limit: number = 10
): Promise<Bill[]> {
  const response = await apiClient.get<Bill[]>(`/users/${userId}/bills`, {
    params: { page, limit },
  });
  return response.data;
}

export async function closeBill(billId: number): Promise<Bill> {
  const response = await apiClient.patch<Bill>(`/bills/${billId}/close`);
  return response.data;
}

/**
 * Split bill total equally among all participants
 */
export async function splitEqually(billId: number): Promise<BillParticipant[]> {
  const response = await apiClient.post<BillParticipant[]>(`/bills/${billId}/split-equally`);
  return response.data;
}

/**
 * Generate invite link for a bill
 */
export function generateInviteLink(billId: number): string {
  const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
  return `${baseUrl}/join/${billId}`;
}

/**
 * Generate Telegram share link (Direct Mini App link)
 */
export function generateTelegramShareLink(billId: number, billTitle: string): string {
  const botUsername = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || 'SplitTheBillsBot';
  const cleanUsername = botUsername.startsWith('@') ? botUsername.slice(1) : botUsername;
  
  const text = encodeURIComponent(`Join my bill: ${billTitle}`);
  // Deep link format: https://t.me/botusername/appname?startapp=join_123
  // Using the standard share link with startapp parameter
  return `https://t.me/share/url?url=https://t.me/${cleanUsername}/app?startapp=join_${billId}&text=${text}`;
}

/**
 * Join a bill as current user
 */
export async function joinBill(billId: number, userId: number): Promise<BillParticipant> {
  const response = await apiClient.post<BillParticipant>(`/bills/${billId}/join`, {
    user_id: userId
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
): Promise<BillParticipant> {
  const response = await apiClient.post<BillParticipant>(
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
 * Split the remainder of the bill among selected participants
 */
export async function splitRemainder(
  billId: number,
  participantIds: number[]
): Promise<BillParticipant[]> {
  const response = await apiClient.post<BillParticipant[]>(
    `/bills/${billId}/split-remainder`,
    {
      participant_ids: participantIds,
    }
  );
  return response.data;
}

/**
 * Send a reaction to a bill
 */
export async function sendReaction(
  billId: number,
  userId: number,
  emoji: string
): Promise<void> {
  await apiClient.post(`/bills/${billId}/reactions`, {
    user_id: userId,
    emoji: emoji,
  });
}
