// API Response Types based on backend models

export interface User {
  id: number;
  telegram_id: number;
  username: string | null;
  avatar_url: string | null;
}

export interface UserCreate {
  telegram_id: number;
  username?: string | null;
  avatar_url?: string | null;
}

export enum SplitType {
  MANUAL = 'manual',
  EQUALLY = 'equally',
}

export interface Bill {
  id: number;
  owner_id: number;
  total_sum: number;
  title: string | null;
  payment_details: string | null;
  participants_count: number;
  is_closed: boolean;
  created_at: string;
  split_type: SplitType;
  unallocated_sum: number;
}

export interface BillCreate {
  owner_id: number;
  total_sum: number;
  title?: string | null;
  payment_details?: string | null;
  include_owner?: boolean;
}

export interface BillItem {
  id: number;
  bill_id: number;
  name: string;
  price: number;
  count: number;
  item_sum: number;
  assigned_to_user_id: number | null;
}

export interface BillItemCreate {
  name: string;
  price: number;
  count: number;
  assigned_to_user_id?: number | null;
}

export interface BillParticipant {
  id: number;
  bill_id: number;
  user_id: number | null;
  guest_name: string | null;
  allocated_amount: number;
  is_paid: boolean;
}

export interface BillParticipantCreate {
  user_id?: number | null;
  guest_name?: string | null;
  allocated_amount?: number;
}

export interface BillDetail extends Bill {
  items: BillItem[];
  participants: BillParticipant[];
}

// Frontend-specific types
export interface BillWithRole extends Bill {
  role: "creator" | "participant";
}
