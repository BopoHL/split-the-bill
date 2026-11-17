// API Response Types based on backend models

import type { Currency } from '@/lib/utils/currencyCatalog';
import type { Theme } from '@/lib/utils/themes';

export interface UserSettings {
  theme?: Theme;
  language?: 'en' | 'ru' | 'uz';
  currency?: Currency;
  /** Set once the user has finished (or skipped) the first-run onboarding. */
  onboarding_completed?: boolean;
  /** Set once the user has finished (or skipped) the tour of a bill they joined. */
  guest_tour_completed?: boolean;
  /** Set by the server once the bot has sent its one-time onboarding DM. */
  welcome_sent?: boolean;
  /** Set when Telegram rejected bot messages; opening an invite can clear it. */
  bot_blocked?: boolean;
  /** The badge picked to show by their name: «none», «pro» or an analytics title's key. */
  badge?: string;
}

export interface ParticipantPreview {
  initial: string;
  avatar_url: string | null;
}

export interface User {
  id: number;
  telegram_id: number;
  username: string | null;
  name: string | null;
  surname: string | null;
  avatar_url: string | null;
  settings?: UserSettings | null;
}

export interface UserCreate {
  telegram_id: number;
  username?: string | null;
  name?: string | null;
  surname?: string | null;
  avatar_url?: string | null;
  allows_write_to_pm?: boolean | null;
}

export interface PaymentMethod {
  id: number;
  label: string | null;
  value: string;
}

export interface PaymentMethodCreate {
  value: string;
  label?: string | null;
}

export enum SplitType {
  MANUAL = 'manual',
  BY_ITEMS = 'by_items',
}

export enum BillStatus {
  OPEN = 'open',
  PAID = 'paid',
  CLOSED = 'closed',
}

export interface Bill {
  id: number;
  owner_id: number;
  total_sum: number;
  title: string | null;
  payment_details: string | null;
  participants_count: number;
  status: BillStatus;
  created_at: string;
  split_type: SplitType;
  /** Currency bound to the bill at creation (uzs/usd/rub). */
  currency?: Currency;
  unallocated_sum: number;
  public_token: string;
  expected_people?: number | null;
  // Dashboard-card aggregates (present on the list endpoint).
  items_count?: number;
  paid_count?: number;
  /** Same counts with the owner excluded — what the "n/x paid" chip shows. */
  payers_count?: number;
  payers_paid?: number;
  participants_preview?: ParticipantPreview[];
  /** Said for whoever listed their bills (the list endpoint only). */
  my_seat?: ViewerSeat | null;
  owner?: BillOwner | null;
  collection?: BillCollection | null;
}

/** The listing user's own seat on a bill they sit at. */
export interface ViewerSeat {
  id: number;
  amount: number;
  is_paid: boolean;
}

export interface BillOwner {
  name: string | null;
  avatar_url: string | null;
}

/** The owner's open bill: what is still owed and whom they may remind now. */
export interface BillCollection {
  left: number;
  remindable: number;
  reminded_at: string | null;
  next_reminder_at: string | null;
}

export interface BillCounts {
  all: number;
  owned: number;
  joined: number;
}

export interface BillCreate {
  owner_id: number;
  total_sum: number;
  title?: string | null;
  payment_details?: string | null;
  expected_people?: number | null;
  include_owner?: boolean;
  /** Currency chosen while creating the new bill. */
  currency?: Currency;
}

export interface BillUpdate {
  title?: string | null;
  payment_details?: string | null;
  expected_people?: number | null;
  currency?: Currency | null;
  user_id: number;
}

export interface BillItem {
  id: number;
  bill_id: number;
  name: string;
  price: number;
  count: number;
  item_sum: number;
  is_shared_globally: boolean;
  /** Seats assigned to any portion. Seats, not accounts — a guest has no account. */
  assigned_participant_ids: number[];
  /** Per-portion assignees: length `count`, each the participant ids sharing that portion. */
  portions?: number[][];
  /** Which receipt brought this line in; null for hand-added ones. */
  receipt_task_id?: number | null;
}

export interface BillItemCreate {
  name: string;
  price: number;
  count: number;
}

export interface BillItemUpdate {
  name?: string;
  price?: number;
  count?: number;
  is_shared_globally?: boolean;
}

export interface BillItemPositionParams {
  portion_index: number;
  expected_count: number;
}

/** The last reminder the owner sent a seat by hand, and how it went. */
export interface ParticipantReminder {
  status: 'pending' | 'sent' | 'failed';
  /** When it was asked for. */
  at: string;
  failure: 'unreachable' | 'no_senders' | 'settled' | 'error' | null;
  /** Until when another one cannot be sent; null when it can be now. */
  next_at: string | null;
}

export interface ReminderRequestResult {
  queued: number;
  skipped: { participant_id: number; reason: 'guest' | 'owner' | 'paid' | 'nothing_owed' | 'cooldown' }[];
}

/** What others owe the user on their open bills: shares not yet paid. */
/** Why there is nobody to remind, and nobody to wait for: the step that would bring somebody. */
export type WhyNobody = 'no_bills' | 'no_people' | 'unassigned' | 'guests' | 'all_paid';

export interface OwedSummary {
  totals: { currency: Currency; amount: number }[];
  people: number;
  bills: number;
  /** Of those people, how many a reminder can go to right now. */
  remindable: number;
  /** When the first of those reminded lately may be reminded again. */
  next_reminder_at?: string | null;
  why_nobody?: WhyNobody | null;
}

export interface BillParticipant {
  id: number;
  bill_id: number;
  user_id: number | null;
  guest_name: string | null;
  username: string | null;
  name: string | null;
  surname: string | null;
  avatar_url: string | null;
  allocated_amount: number;
  is_paid: boolean;
  /** Position at the table; the owner is always 0. */
  seat_index: number;
  /** True while no account occupies this seat. */
  is_guest: boolean;
  claimed_at: string | null;
  reminder?: ParticipantReminder | null;
  /** The badge by their name: «pro» or an analytics title's key. */
  badge?: string | null;
}

export interface SeatItemPreview {
  name: string;
  share: number;
}

/** A seat as shown to someone deciding where to sit, before they're in the bill. */
export interface SeatPreview {
  id: number;
  seat_index: number;
  guest_name: string | null;
  display_name: string | null;
  avatar_url: string | null;
  is_taken: boolean;
  is_me: boolean;
  allocated_amount: number;
  items: SeatItemPreview[];
}

export interface Receipt {
  task_id: number;
  /** Position on the bill — recomputed after a deletion, so no gaps. */
  index: number;
  /** `manual_photo` was attached without recognition — nothing to rate or reconcile. */
  source: 'photo' | 'soliq_qr' | 'manual_photo';
  status: 'pending' | 'processing' | 'structuring' | 'completed' | 'failed' | 'cancelled';
  merchant_name: string | null;
  total: number | null;
  items_count: number;
  quality: number | null;
  has_photo: boolean;
  created_at: string;
}

export interface ReceiptDeleteImpact {
  items_count: number;
  total: number;
  assigned_count: number;
}

export interface BillSeats {
  bill_id: number;
  title: string | null;
  currency: Currency;
  status: BillStatus;
  seats: SeatPreview[];
}

/** Somebody the owner may seat, as the assign picker lists them. */
export interface AssignableUser {
  user_id: number;
  username: string | null;
  name: string | null;
  surname: string | null;
  avatar_url: string | null;
}

export interface BillParticipantCreate {
  user_id?: number | null;
  guest_name?: string | null;
  allocated_amount?: number;
}

export interface BillDetail extends Bill {
  items: BillItem[];
  participants: BillParticipant[];
  /** What the others still owe the owner: the figure the home screen shows too. */
  left_to_collect?: number;
  /** A bill can hold several receipts; each keeps its own items. */
  receipts?: Receipt[];
  /** Made by the guided tour; it has no life outside it. */
  is_demo?: boolean;
  /** Where the bill was run up, when known. */
  place?: string | null;
  is_ai_scanned?: boolean;
  scan_quality?: number | null;
  /** Grand total printed on the scanned receipt (currency units). */
  receipt_total_sum?: number | null;
  /** Sum of AI-scanned items disagrees with the receipt's printed total. */
  scan_total_mismatch?: boolean;
  /** total − unallocated, computed server-side. */
  allocated_sum?: number;
}

// Frontend-specific types
export interface BillWithRole extends Bill {
  role: "creator" | "participant";
}
