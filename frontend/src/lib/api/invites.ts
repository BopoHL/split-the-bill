import apiClient from './client';

export type InviteChannel = 'link' | 'qr' | 'prepared' | 'seat' | 'bot';

export interface Invite {
  code: string;
  channel: InviteChannel;
  deep_link: string;
}

export interface ResolvedInvite {
  code: string;
  channel: InviteChannel;
  bill_id: number;
  public_token: string;
  seat_participant_id: number | null;
  inviter_user_id: number;
  inviter_name: string | null;
}

/**
 * Mint a share of this bill.
 *
 * The bill's public token is the same for everyone at the table, so a link
 * built from it cannot say who shared it. A minted invite can.
 */
export async function createInvite(
  billId: number,
  channel: InviteChannel,
  seatParticipantId?: number,
): Promise<Invite> {
  const response = await apiClient.post<Invite>(`/bills/${billId}/invites`, {
    channel,
    seat_participant_id: seatParticipantId ?? null,
  });
  return response.data;
}

export async function resolveInvite(code: string): Promise<ResolvedInvite> {
  const response = await apiClient.get<ResolvedInvite>(`/invites/${code}`);
  return response.data;
}
