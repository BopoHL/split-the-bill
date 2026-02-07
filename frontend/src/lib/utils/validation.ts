import { z } from 'zod';

// Bill creation validation
export const billCreateSchema = z.object({
  title: z.string().min(1, 'Title is required').max(100, 'Title too long'),
  total_sum: z.number().min(1, 'Amount must be greater than 0'),
  payment_details: z.string().optional(),
  include_creator: z.boolean().default(false),
});

export type BillCreateFormData = z.infer<typeof billCreateSchema>;

// Bill item validation
export const billItemSchema = z.object({
  name: z.string().min(1, 'Item name is required').max(100, 'Name too long'),
  price: z.number().min(1, 'Price must be greater than 0'),
});

export type BillItemFormData = z.infer<typeof billItemSchema>;

// Participant validation
export const participantSchema = z.object({
  name: z.string().min(1, 'Name is required').max(50, 'Name too long'),
});

export type ParticipantFormData = z.infer<typeof participantSchema>;

// Payment confirmation validation
export const paymentConfirmSchema = z.object({
  confirmed: z.boolean().refine((val) => val === true, {
    message: 'You must confirm the payment',
  }),
});

export type PaymentConfirmFormData = z.infer<typeof paymentConfirmSchema>;
