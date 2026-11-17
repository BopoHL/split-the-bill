import { BillStatus, SplitType, type Bill, type BillDetail, type BillItem, type BillParticipant } from '@/types/api';

export const participantFixture = (overrides: Partial<BillParticipant> = {}): BillParticipant => ({
  id: 1, bill_id: 1, user_id: 10, guest_name: null, username: 'alice', name: 'Alice', surname: null,
  avatar_url: null, allocated_amount: 0, is_paid: false, seat_index: 0, is_guest: false, claimed_at: null,
  ...overrides,
});

export const itemFixture = (overrides: Partial<BillItem> = {}): BillItem => ({
  id: 1, bill_id: 1, name: 'Pizza', price: 1000, count: 1, item_sum: 1000,
  is_shared_globally: false, assigned_participant_ids: [], portions: [[]], ...overrides,
});

export const billFixture = (overrides: Partial<BillDetail> = {}): BillDetail => ({
  id: 1, owner_id: 10, title: 'Dinner', total_sum: 1000, payment_details: null,
  participants_count: 2, expected_people: 2, status: BillStatus.OPEN,
  created_at: '2026-09-18T12:00:00Z', split_type: SplitType.BY_ITEMS, currency: 'uzs',
  unallocated_sum: 1000, public_token: 'test-only',
  participants: [participantFixture(), participantFixture({ id: 2, user_id: 20, username: 'bob', name: 'Bob', seat_index: 1 })],
  items: [itemFixture()], receipts: [], ...overrides,
});

/** A bill as the home lists get it, with the viewer's place on it. */
export const listedBillFixture = (overrides: Partial<Bill> = {}): Bill => ({
  id: 1, owner_id: 10, title: 'Dinner', total_sum: 1000, payment_details: null,
  participants_count: 2, expected_people: 2, status: BillStatus.OPEN,
  created_at: '2026-09-18T12:00:00Z', split_type: SplitType.BY_ITEMS, currency: 'uzs',
  unallocated_sum: 0, public_token: 'test-only', payers_count: 1, payers_paid: 0,
  my_seat: null, owner: { name: 'Alice', avatar_url: null }, collection: null, ...overrides,
});
