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
 * Get user by Telegram ID
 */
export async function getUserByTelegramId(telegramId: number): Promise<User | null> {
  try {
    // Backend doesn't have this endpoint yet, so we'll use create/update which returns existing user
    const response = await apiClient.post<User>('/users/', {
      telegram_id: telegramId,
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching user by Telegram ID:', error);
    return null;
  }
}
