import apiClient from './client';
import type { OwedSummary, ReminderRequestResult } from '@/types/api';

/**
 * Owner only: remind one seat, or everyone on the bill who still owes when no
 * seat is named. They go out within seconds; the seat's `reminder` says how.
 */
export async function sendReminders(billId: number, participantId?: number): Promise<ReminderRequestResult> {
  const response = await apiClient.post<ReminderRequestResult>(`/bills/${billId}/reminders`, {
    participant_id: participantId ?? null,
  });
  return response.data;
}

export async function getOwed(userId: number): Promise<OwedSummary> {
  const response = await apiClient.get<OwedSummary>(`/users/${userId}/owed`);
  return response.data;
}

/** A reminder to everyone who owes the user on any open bill. */
export async function remindEveryoneWhoOwes(userId: number): Promise<ReminderRequestResult> {
  const response = await apiClient.post<ReminderRequestResult>(`/users/${userId}/owed/reminders`);
  return response.data;
}
