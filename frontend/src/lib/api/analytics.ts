import apiClient from './client';
import type { Analytics, AnalyticsPeriodQuery, AnalyticsPictures } from '@/types/analytics';

const periodParams = (period: AnalyticsPeriodQuery) => ({ period: period.kind, year: period.year, month: period.month });

export async function getAnalytics(userId: number, period: AnalyticsPeriodQuery): Promise<Analytics> {
  const response = await apiClient.get<Analytics>(`/users/${userId}/analytics`, {
    params: periodParams(period),
  });
  return response.data;
}

/** Where the period's report receipt and, for a year, its stories are drawn. */
export async function getAnalyticsPictures(userId: number, period: AnalyticsPeriodQuery): Promise<AnalyticsPictures> {
  const response = await apiClient.get<AnalyticsPictures>(`/users/${userId}/analytics/pictures`, {
    params: periodParams(period),
  });
  return response.data;
}

/** The period's receipt registered as a photo to send, for WebApp.shareMessage. */
export async function prepareAnalyticsShare(userId: number, period: AnalyticsPeriodQuery): Promise<string> {
  const response = await apiClient.post<{ prepared_message_id: string }>(`/users/${userId}/analytics/prepare-share`, null, {
    params: periodParams(period),
  });
  return response.data.prepared_message_id;
}

/** The places the user's bills were at, the latest first. */
export async function getPlaces(userId: number): Promise<string[]> {
  const response = await apiClient.get<string[]>(`/users/${userId}/places`);
  return response.data;
}

/** Owner only: where the bill was; empty says nowhere in particular. */
export async function setBillPlace(billId: number, name: string): Promise<string | null> {
  const response = await apiClient.put<{ place: string | null }>(`/bills/${billId}/place`, { name });
  return response.data.place;
}
