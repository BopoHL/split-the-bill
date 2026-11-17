import apiClient from './client';
import type { ProOverview, ProPlan } from '@/types/pro';

export async function getPro(userId: number): Promise<ProOverview> {
  const response = await apiClient.get<ProOverview>(`/users/${userId}/pro`);
  return response.data;
}

/** Pro as it stands, with the viewer's one-off offer made if they may have one. */
export async function startProOffer(userId: number): Promise<ProOverview> {
  const response = await apiClient.post<ProOverview>(`/users/${userId}/pro/offer`);
  return response.data;
}

/** A Stars invoice for the plan, to open with WebApp.openInvoice. */
export async function createProInvoice(userId: number, plan: ProPlan): Promise<string> {
  const response = await apiClient.post<{ link: string }>(`/users/${userId}/pro/invoice`, { plan });
  return response.data.link;
}

export async function redeemPromo(userId: number, code: string): Promise<ProOverview> {
  const response = await apiClient.post<ProOverview>(`/users/${userId}/pro/redeem`, { code });
  return response.data;
}
