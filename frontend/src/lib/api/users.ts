import apiClient from './client';
import type { User, UserCreate } from '@/types/api';

/**
 * Create or update user based on telegram_id
 */
export async function createOrUpdateUser(userData: UserCreate): Promise<User> {
  const response = await apiClient.post<User>('/users/', userData);
  return response.data;
}

/**
 * Get user by ID
 */
export async function getUser(userId: number): Promise<User> {
  const response = await apiClient.get<User>(`/users/${userId}`);
  return response.data;
}

/**
 * Get user by Telegram ID (creates/updates if not exists)
 */
export async function getUserByTelegramId(
  telegramId: number, 
  username?: string, 
  avatarUrl?: string
): Promise<User | null> {
  try {
    const response = await apiClient.post<User>('/users/', {
      telegram_id: telegramId,
      username: username,
      avatar_url: avatarUrl,
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching/syncing user by Telegram ID:', error);
    return null;
  }
}
