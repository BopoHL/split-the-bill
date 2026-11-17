import apiClient from './client';
import type { Currency } from '@/lib/utils/currencyCatalog';

export interface ReceiptTaskResponse {
  id: number;
  user_id: number | null;
  filename: string | null;
  status: string;
  bill_id: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export const receiptsApi = {
  upload: async (
    file: File,
    userId?: number,
    expectedPeople?: number,
    paymentDetails?: string,
    /** Scan INTO an existing bill — adds another receipt instead of creating one. */
    billId?: number,
    /** Currency for a newly-created scanned bill. Ignored when billId is set. */
    currency?: Currency,
  ): Promise<ReceiptTaskResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (userId) {
      formData.append('user_id', userId.toString());
    }
    if (billId != null) {
      formData.append('bill_id', billId.toString());
    }
    if (expectedPeople != null) {
      formData.append('expected_people', expectedPeople.toString());
    }
    if (paymentDetails) {
      formData.append('payment_details', paymentDetails);
    }
    if (currency) {
      formData.append('currency', currency);
    }

    const response = await apiClient.post<ReceiptTaskResponse>('/receipts/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      // Photos are several MB; a slow mobile uplink needs far more than the
      // default timeout, otherwise the request is aborted mid-upload.
      timeout: 60000,
    });
    return response.data;
  },

  /**
   * Import a bill from an Uzbek fiscal (Soliq) receipt QR. `qrUrl` is the
   * scanned ofd.soliq.uz check link; the backend validates it, creates a UZS
   * bill and reads the items from the check page (same SSE flow as a photo scan).
   */
  uploadQr: async (
    qrUrl: string,
    userId?: number,
    expectedPeople?: number,
    paymentDetails?: string,
    /** Import INTO an existing bill — adds another receipt to it. */
    billId?: number,
  ): Promise<ReceiptTaskResponse> => {
    const formData = new FormData();
    formData.append('qr_url', qrUrl);
    if (userId) {
      formData.append('user_id', userId.toString());
    }
    if (billId != null) {
      formData.append('bill_id', billId.toString());
    }
    if (expectedPeople != null) {
      formData.append('expected_people', expectedPeople.toString());
    }
    if (paymentDetails) {
      formData.append('payment_details', paymentDetails);
    }

    const response = await apiClient.post<ReceiptTaskResponse>(
      '/receipts/upload-qr',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 30000 },
    );
    return response.data;
  },

  /** Cancel a scan the user gave up on (20s timeout), so the worker doesn't
   *  create an orphan bill after the user moved to manual entry. */
  cancelTask: async (taskId: number): Promise<void> => {
    await apiClient.post(`/receipts/tasks/${taskId}/cancel`);
  },

  /**
   * Attach a receipt photo to an existing bill (no AI parsing). Owner only.
   */
  attachToBill: async (billId: number, file: File, userId: number): Promise<void> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', userId.toString());
    await apiClient.post(`/bills/${billId}/receipt`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    });
  },

  getStreamUrl: (taskId: number, ticket: string): string => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    return `${baseUrl}/receipts/tasks/${taskId}/stream?ticket=${encodeURIComponent(ticket)}`;
  }
};
