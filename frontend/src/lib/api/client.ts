import axios from 'axios';
import { getTelegramWebApp } from '../telegram/init';

// Create axios instance with base configuration
const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
  // 30s default — 10s was too tight for Telegram on mobile/cellular (TLS +
  // slow links made ordinary calls abort). File uploads override this with an
  // even longer per-request timeout (see receiptsApi).
  timeout: 30000,
});

// Request interceptor to add Telegram auth data
apiClient.interceptors.request.use(
  (config) => {
    const webApp = getTelegramWebApp();
    
    if (webApp?.initData) {
      // Add Telegram initData to headers for backend validation
      config.headers['X-Telegram-Init-Data'] = webApp.initData;
    }
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/** What a 402 says is missing: Pro for a feature, or the day's free scans. */
export interface PaymentRequired {
  code: 'PRO_REQUIRED' | 'SCAN_LIMIT';
  feature?: string;
  limit?: number;
}

/** Whether a failed request was refused for want of Pro or of free scans. */
export function isPaymentRequired(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 402;
}

let onPaymentRequired: ((detail: PaymentRequired) => void) | null = null;

/** Who hears about a request that needs Pro — the paywall. */
export function setPaymentRequiredHandler(handler: ((detail: PaymentRequired) => void) | null): void {
  onPaymentRequired = handler;
}

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response?.status === 402 && error.response.data?.detail?.code) {
      onPaymentRequired?.(error.response.data.detail as PaymentRequired);
    }
    if (error.response) {
      // Server responded with error status
      const message = error.response.data?.detail || error.response.data?.message || 'An error occurred';
      console.error('API Error:', message);
      
      // You can add toast notifications here
      // toast.error(message);
    } else if (error.request) {
      // Request was made but no response received
      console.error('Network Error:', error.message);
      // toast.error('Network error. Please check your connection.');
    } else {
      // Something else happened
      console.error('Error:', error.message);
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
