import apiClient from './client';

export interface AppConfig {
  /** Whom «Contact support» opens a chat with. */
  support_username: string;
}

/** What an operator decides for the app, from the admin panel. */
export async function getAppConfig(): Promise<AppConfig> {
  const response = await apiClient.get<AppConfig>('/app-config');
  return response.data;
}
