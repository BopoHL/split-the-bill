import apiClient from './client';

export interface ProfileBadge {
  key: string;
  value: number | null;
  subject: string | null;
}

export interface ProfileBadges {
  /** «none», a badge's key, or null while nothing is picked. */
  chosen: string | null;
  shown: string | null;
  available: ProfileBadge[];
}

/** The badges the user may show by their name, and the one they show. */
export async function getBadges(userId: number): Promise<ProfileBadges> {
  const response = await apiClient.get<ProfileBadges>(`/users/${userId}/badges`);
  return response.data;
}

/** Show this badge by their name — «none» for none, null for the default. */
export async function chooseBadge(userId: number, badge: string | null): Promise<ProfileBadges> {
  const response = await apiClient.put<ProfileBadges>(`/users/${userId}/badge`, { badge });
  return response.data;
}
