import apiClient from './client';
import type { BillDetail } from '@/types/api';
import type { Language } from '@/lib/i18n/translations';

/** A demo bill for the guided tour, «scanned» from a prepared receipt, with
 *  the card the tour typed in. */
export async function createDemoBill(language: Language, paymentDetails?: string): Promise<BillDetail> {
  const response = await apiClient.post<BillDetail>('/demo-bills/', {
    language,
    payment_details: paymentDetails ?? null,
  });
  return response.data;
}

/** The tour's pretend invite: its friends take the empty seats. */
export async function seatDemoFriends(billId: number, language: Language): Promise<BillDetail> {
  const response = await apiClient.post<BillDetail>(`/demo-bills/${billId}/friends`, { language });
  return response.data;
}

export async function eraseDemoBill(billId: number): Promise<void> {
  await apiClient.delete(`/demo-bills/${billId}`);
}
