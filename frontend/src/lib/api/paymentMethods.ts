import apiClient from './client';
import type { PaymentMethod, PaymentMethodCreate } from '@/types/api';

/** A user's saved payment methods (values are decrypted server-side for the owner). */
export async function listPaymentMethods(
  userId: number,
): Promise<PaymentMethod[]> {
  const res = await apiClient.get<PaymentMethod[]>(
    `/users/${userId}/payment-methods/`,
  );
  return res.data;
}

export async function createPaymentMethod(
  userId: number,
  data: PaymentMethodCreate,
): Promise<PaymentMethod> {
  const res = await apiClient.post<PaymentMethod>(
    `/users/${userId}/payment-methods/`,
    data,
  );
  return res.data;
}

export async function deletePaymentMethod(
  userId: number,
  methodId: number,
): Promise<void> {
  await apiClient.delete(`/users/${userId}/payment-methods/${methodId}`);
}
