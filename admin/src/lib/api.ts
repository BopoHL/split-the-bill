/**
 * Thin client for /api/admin.
 *
 * The session lives in an httpOnly cookie, so nothing here handles a token — the
 * browser attaches it and a 401 simply means "log in again".
 */
const BASE = process.env.NEXT_PUBLIC_ADMIN_API_URL || '/api/admin';

export class Unauthorized extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // An upload must set its own multipart boundary, so the JSON content type is
  // only added when the body is not a form.
  const isForm = init?.body instanceof FormData;
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers ?? {}),
    },
  });

  if (response.status === 401) {
    // The session ran out mid-work: the shell goes back to the login form
    // instead of each screen showing an empty error.
    window.dispatchEvent(new Event('admin:unauthorized'));
    throw new Unauthorized('Сессия истекла');
  }
  if (!response.ok) throw new Error(failureMessage(await response.text()));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/** The API's own words for what went wrong — FastAPI wraps them in `detail`. */
function failureMessage(body: string): string {
  try {
    const { detail } = JSON.parse(body) as { detail?: unknown };
    if (typeof detail === 'string') return detail;
  } catch {
    /* not JSON: the body is the message */
  }
  return body;
}

export interface Stats {
  users_total: number;
  users_new_7d: number;
  bills_total: number;
  bills_open: number;
  bills_closed: number;
  bills_deleted: number;
  scans_total: number;
  scans_failed: number;
  average_bill: number;
}

export interface BillRow {
  id: number;
  title: string | null;
  owner_id: number;
  owner: string | null;
  status: string;
  currency: string;
  total_sum: number;
  participants_count: number;
  items_count: number;
  receipts_count: number;
  is_deleted: boolean;
  created_at: string;
}

export interface UserRow {
  id: number;
  telegram_id: number;
  username: string | null;
  name: string | null;
  surname: string | null;
  avatar_url: string | null;
  language: string | null;
  currency: string | null;
  onboarding_completed: boolean;
  bot_blocked: boolean;
  bills_count: number;
  participant_bills_count: number;
  created_at: string;
}

export interface FeedbackRow {
  id: number;
  message: string;
  /** What the person typed into the form's name field. */
  name: string | null;
  created_at: string;
  user_id: number | null;
  user: string | null;
  telegram_id: number | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ReceiptSummary {
  task_id: number;
  index: number;
  source: string;
  status: string;
  merchant_name: string | null;
  total: number | null;
  items_count: number;
  quality: number | null;
  has_photo: boolean;
  created_at: string;
}

export interface BillItem {
  id: number;
  bill_id: number;
  name: string;
  price: number;
  count: number;
  item_sum: number;
  is_shared_globally: boolean;
  assigned_participant_ids: number[];
  receipt_task_id: number | null;
  portions: number[][];
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
  seat_index: number;
  is_guest: boolean;
  claimed_at: string | null;
}

export interface BillDetail {
  id: number;
  owner_id: number;
  owner: string | null;
  total_sum: number;
  title: string | null;
  split_type: string;
  status: string;
  currency: string;
  unallocated_sum: number;
  allocated_sum: number;
  paid_count: number;
  created_at: string;
  expected_people: number | null;
  has_receipt: boolean;
  is_ai_scanned: boolean;
  scan_quality: number | null;
  receipt_total_sum: number | null;
  scan_total_mismatch: boolean;
  is_deleted: boolean;
  deleted_at: string | null;
  receipts: ReceiptSummary[];
  items: BillItem[];
  participants: BillParticipant[];
}

export interface UserDetail extends UserRow {
  settings: Record<string, unknown>;
  owned_bills: BillRow[];
  participant_bills: BillRow[];
}

/** What the panel may change in someone's settings; null takes a key out. */
export interface UserSettingsChange {
  language?: 'ru' | 'uz' | 'en' | null;
  theme?: 'light' | 'dark' | 'nord' | 'nord_frost' | 'sakura' | 'midnight' | null;
  currency?: string | null;
  onboarding_completed?: boolean | null;
  welcome_sent?: boolean | null;
  bot_blocked?: boolean | null;
  internal?: boolean | null;
}

export type BroadcastFormat = 'message' | 'rich';

export interface BroadcastRow {
  id: number;
  title: string;
  format: BroadcastFormat;
  body: Record<string, string>;
  parse_mode: string | null;
  button_text: string | null;
  button_url: string | null;
  audience: string;
  target_user_ids: number[];
  scheduled_at: string | null;
  has_photo: boolean;
  status: string;
  total_count: number;
  sent_count: number;
  failed_count: number;
  created_at: string;
}

export interface BroadcastRecipient {
  user_id: number;
  username: string | null;
  telegram_id: number | null;
  status: string;
  sent_at: string | null;
  error: string | null;
}

export interface BroadcastDetail extends BroadcastRow {
  target_usernames: string[];
}

/** What a broadcast says and how — the part a test send needs too. */
export interface BroadcastMessage {
  format: BroadcastFormat;
  body: Record<string, string>;
  with_button: boolean;
  button_text?: string;
  button_url?: string;
}

export interface DeliveryFilters {
  status?: string;
  q?: string;
}

export type ReminderState = 'scheduled' | 'muted' | 'stopped';

export interface ReminderRow {
  id: number;
  bill_id: number;
  bill_title: string | null;
  bill_status: string;
  currency: string;
  participant_id: number;
  user_id: number | null;
  username: string | null;
  telegram_id: number | null;
  amount: number;
  is_paid: boolean;
  state: ReminderState;
  sent_count: number;
  last_sent_at: string | null;
  next_due_at: string | null;
  muted_at: string | null;
  created_at: string;
}

export interface RemindersPage extends Page<ReminderRow> {
  sent_total: number;
}

export interface ReminderFilters {
  state?: string;
  only_sent?: boolean;
  q?: string;
  bill_id?: number;
}

export interface ScanRow {
  id: number;
  created_at: string;
  status: string;
  source: string;
  scan_mode: string | null;
  llm_model: string | null;
  user: string | null;
  bill_id: number | null;
  bill_title: string | null;
  scan_quality: number | null;
  items_count: number;
  has_photo: boolean;
  error_message: string | null;
}

export interface ScanItem {
  name: string;
  price: number;
  count: number;
  item_sum: number;
  is_shared_globally: boolean;
}

export interface ScanDetail extends ScanRow {
  ocr_text: string | null;
  llm_response: string | null;
  source_url: string | null;
  bill_total: number | null;
  items: ScanItem[];
}

export interface ScanFilters {
  status?: string;
  source?: string;
  quality?: string;
  mode?: string;
}

/** How a receipt photo gets turned into items. */
export type ScanMode = 'ocr_llm' | 'vision' | 'hybrid';

export interface Settings {
  scan_mode: ScanMode;
  /** The OpenAI model that reads receipts. */
  receipt_model: string;
  /** The OpenAI model that tells what each receipt line is and names the place. */
  label_model: string;
  /** Whom «Contact support» in the app opens a chat with — ours until one is set. */
  support_username: string;
}

export type LabelingHistoryState = 'running' | 'paused' | 'done';

/** The run through what was there before labeling began. */
export interface LabelingHistory {
  state: LabelingHistoryState;
  started_at: string;
  finished_at: string | null;
  lines_done: number;
  lines_total: number;
  bills_done: number;
  bills_total: number;
}

export interface Labeling {
  key_set: boolean;
  model: string;
  /** When labeling began: what came after is labeled on its own. Null until the job first runs. */
  since: string | null;
  last_labeled_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  history: LabelingHistory | null;
}

export type ProPlan = 'month' | 'half_year' | 'year';

export interface ProStats {
  /** Everyone with Pro right now; of them, who paid and who is on the trial. */
  active: number;
  paying: number;
  trial: number;
  stars_last_30_days: number;
  stars_total: number;
}

export interface ProSettings {
  /** Each plan's price in Telegram Stars. */
  prices: Record<ProPlan, number>;
  /** The price shown struck out above it, «down from»; null where there is none. */
  was_prices: Record<ProPlan, number | null>;
  free_scans_per_day: number;
  /** The one-off discount on six months and a year for someone who has never paid; 0 offers none. */
  offer_percent: number;
  offer_hours: number;
  stats: ProStats;
}

export interface ProSettingsChange {
  prices?: Partial<Record<ProPlan, number>>;
  /** A null takes the plan's «was» price away. */
  was_prices?: Partial<Record<ProPlan, number | null>>;
  free_scans_per_day?: number;
  offer_percent?: number;
  offer_hours?: number;
}

export interface PromoCode {
  id: number;
  code: string;
  days: number;
  /** Null: as many people as like. */
  max_uses: number | null;
  uses: number;
  expires_at: string | null;
  is_active: boolean;
  note: string | null;
  created_at: string;
}

export interface PromoCodeDraft {
  /** Left out, the server makes one up. */
  code?: string;
  days: number;
  max_uses?: number;
  expires_at?: string;
  note?: string;
}

export type ProSource = 'trial' | 'purchase' | 'subscription' | 'promo';
export type ProGrantState = 'active' | 'upcoming' | 'ended' | 'revoked' | 'refunded';
export type ProGrantAction = 'revoke' | 'refund' | 'stop_renewal' | 'allow_renewal';

/** One stretch of Pro someone has or had, and what the server lets the admin do with it. */
export interface ProGrant {
  id: number;
  user: { id: number; telegram_id: number; username: string | null; name: string | null };
  source: ProSource;
  plan: ProPlan | null;
  days: number | null;
  stars: number | null;
  promo_code: string | null;
  starts_at: string;
  ends_at: string;
  created_at: string;
  revoked_at: string | null;
  refunded_at: string | null;
  subscription_id: number | null;
  renewal_canceled_at: string | null;
  state: ProGrantState;
  actions: ProGrantAction[];
}

export interface ProGrantFilters {
  source?: ProSource;
  /** Only what is on now or queued. */
  running?: boolean;
  user_id?: number;
  q?: string;
}

export interface ScanModeStat {
  mode: string;
  scans: number;
  failed: number;
  /** Share of scans whose printed total disagreed with the items read out of it. */
  mismatch_rate: number | null;
  avg_quality: number | null;
  rated: number;
}

/** Where the bot's queue of Telegram updates stands right now. */
export interface BotQueue {
  /** Updates the bot's worker handles at once. */
  slots: number;
  waiting: number;
  in_hand: number;
  /** Payments waiting to be tried again after failing. */
  retrying: number;
  oldest_waiting_at: string | null;
  handled_last_hour: number;
  failed_last_day: number;
  /** Payments given up on: Stars taken, no Pro given — to be settled by hand. */
  unsettled_payments: number;
}

export type BotUpdateView = 'queue' | 'failed' | 'payments' | 'all';
export type BotUpdateState = 'waiting' | 'in_hand' | 'retry_later' | 'handled' | 'failed' | 'settled';
export type BotUpdateKind =
  | 'command'
  | 'message'
  | 'photo'
  | 'button'
  | 'post_button'
  | 'shared_post'
  | 'membership'
  | 'payment'
  | 'other';
export type BotUpdateAction = 'retry' | 'settle';

export interface BotUpdate {
  update_id: number;
  /** What it keeps its order with: `chat:<id>`, `post:<code>`, `payment:<telegram id>`. */
  lane: string;
  kind: BotUpdateKind;
  who: string | null;
  what: string | null;
  received_at: string;
  attempts: number;
  state: BotUpdateState;
  not_before: string | null;
  claimed_until: string | null;
  done_at: string | null;
  settled_at: string | null;
  error: string | null;
  payload: Record<string, unknown>;
  actions: BotUpdateAction[];
}

function pageParams(page: number, limit: number): string {
  const offset = Math.max(0, page - 1) * limit;
  return `limit=${limit}&offset=${offset}`;
}

function query(filters: Record<string, string | number | boolean | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '' && value !== false) params.set(key, String(value));
  }
  return params.size ? `&${params}` : '';
}

export interface PlaceRow {
  id: number;
  name: string;
  bills: number;
  people: number;
  first_bill_at: string | null;
  last_bill_at: string | null;
}

export type DishGroup = 'food' | 'drink' | 'dessert' | 'alcohol' | 'fee' | 'discount' | 'other';

export interface DishRow {
  name_key: string;
  group: DishGroup;
  kind: string | null;
  kind_name: string | null;
  /** The model that labelled it, or «admin» once corrected here. */
  model: string | null;
  /** How many receipt lines carry this wording. */
  lines: number;
  updated_at: string;
}

export interface DishFilters {
  q?: string;
  group?: string;
  kind?: string;
}

export interface DishKind {
  key: string;
  ru: string;
  uz: string;
  en: string;
}

export type SenderStatus = 'awaiting_code' | 'awaiting_password' | 'active' | 'resting' | 'banned' | 'disabled';

/** A Telegram account that delivers a reminder when the person blocked the bot. */
export interface SenderAccount {
  id: number;
  phone: string;
  telegram_id: number | null;
  username: string | null;
  display_name: string | null;
  status: SenderStatus;
  rest_until: string | null;
  last_error: string | null;
  last_used_at: string | null;
  sent_count: number;
  created_at: string;
}

export interface SenderAccounts {
  /** False until TG_API_ID / TG_API_HASH are set: nothing can be logged in. */
  configured: boolean;
  accounts: SenderAccount[];
}

export interface SenderLoginCode {
  code: string | null;
  received_at: string | null;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ ok: true }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ ok: true }>('/auth/logout', { method: 'POST' }),
  me: () => request<{ email: string }>('/me'),
  stats: () => request<Stats>('/stats'),
  bills: (includeDeleted = false, page = 1, limit = 50) =>
    request<Page<BillRow>>(`/bills?include_deleted=${includeDeleted}&${pageParams(page, limit)}`),
  bill: (id: number) => request<BillDetail>(`/bills/${id}`),
  restoreBill: (id: number) => request<BillRow>(`/bills/${id}/restore`, { method: 'POST' }),
  billReceiptPhotoUrl: (billId: number, taskId: number) =>
    `${BASE}/bills/${billId}/receipts/${taskId}/photo`,
  users: (page = 1, limit = 50) => request<Page<UserRow>>(`/users?${pageParams(page, limit)}`),
  user: (id: number) => request<UserDetail>(`/users/${id}`),
  saveUserSettings: (id: number, change: UserSettingsChange) =>
    request<UserDetail>(`/users/${id}/settings`, { method: 'PUT', body: JSON.stringify(change) }),
  places: (q = '', page = 1, limit = 50) =>
    request<Page<PlaceRow>>(`/places?${pageParams(page, limit)}${query({ q })}`),
  dishes: (filters: DishFilters = {}, page = 1, limit = 50) =>
    request<Page<DishRow>>(`/dishes?${pageParams(page, limit)}${query({ ...filters })}`),
  correctDish: (nameKey: string, group: DishGroup, kind: string | null) =>
    request<DishRow>('/dishes', { method: 'PATCH', body: JSON.stringify({ name_key: nameKey, group, kind }) }),
  dishKinds: () => request<DishKind[]>('/dish-kinds'),
  labeling: () => request<Labeling>('/labeling'),
  startLabelingHistory: () => request<Labeling>('/labeling/history', { method: 'POST' }),
  pauseLabelingHistory: () => request<Labeling>('/labeling/history/pause', { method: 'POST' }),
  createDishKind: (kind: DishKind) =>
    request<DishKind>('/dish-kinds', { method: 'POST', body: JSON.stringify(kind) }),
  feedback: (page = 1, limit = 50) =>
    request<Page<FeedbackRow>>(`/feedback?${pageParams(page, limit)}`),
  broadcasts: () => request<BroadcastRow[]>('/broadcasts'),
  createBroadcast: (payload: BroadcastMessage & {
    title: string;
    audience: string;
    targets?: string[];
    scheduled_at?: string;
  }) => request<BroadcastRow>('/broadcasts', { method: 'POST', body: JSON.stringify(payload) }),
  /** Every language of a draft, sent now to one person; nothing is saved. */
  testBroadcast: (message: BroadcastMessage, target: string, photo: File | null) => {
    const form = new FormData();
    form.append('payload', JSON.stringify({ ...message, target }));
    if (photo) form.append('photo', photo);
    return request<{ sent: string[] }>('/broadcasts/test', { method: 'POST', body: form });
  },
  /** A picture for a rich broadcast; the answer is the address for `<img src>`. */
  uploadBroadcastMedia: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<{ url: string }>('/broadcasts/media', { method: 'POST', body: form });
  },
  sendBroadcast: (id: number) =>
    request<BroadcastRow>(`/broadcasts/${id}/send`, { method: 'POST' }),
  cancelBroadcast: (id: number) =>
    request<BroadcastRow>(`/broadcasts/${id}/cancel`, { method: 'POST' }),
  broadcast: (id: number) => request<BroadcastDetail>(`/broadcasts/${id}`),
  broadcastDeliveries: (id: number, filters: DeliveryFilters = {}, page = 1, limit = 50) =>
    request<Page<BroadcastRecipient>>(
      `/broadcasts/${id}/deliveries?${pageParams(page, limit)}${query({ ...filters })}`,
    ),
  reminders: (filters: ReminderFilters = {}, page = 1, limit = 50) =>
    request<RemindersPage>(`/reminders?${pageParams(page, limit)}${query({ ...filters })}`),
  deleteBroadcast: (id: number) =>
    request<void>(`/broadcasts/${id}`, { method: 'DELETE' }),
  attachBroadcastPhoto: (id: number, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<BroadcastRow>(`/broadcasts/${id}/photo`, { method: 'POST', body: form });
  },
  scans: (filters: ScanFilters = {}) => {
    const params = new URLSearchParams(
      Object.entries(filters).filter(([, value]) => value) as [string, string][],
    );
    return request<ScanRow[]>(`/scans${params.size ? `?${params}` : ''}`);
  },
  scan: (id: number) => request<ScanDetail>(`/scans/${id}`),
  scanModes: () => request<ScanModeStat[]>('/scans/modes'),
  settings: () => request<Settings>('/settings'),
  saveSettings: (payload: Partial<Settings>) =>
    request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  scanPhotoUrl: (id: number) => `${BASE}/scans/${id}/photo`,
  pro: () => request<ProSettings>('/pro'),
  savePro: (change: ProSettingsChange) =>
    request<ProSettings>('/pro', { method: 'PUT', body: JSON.stringify(change) }),
  promoCodes: () => request<PromoCode[]>('/pro/promo-codes'),
  createPromoCode: (draft: PromoCodeDraft) =>
    request<PromoCode>('/pro/promo-codes', { method: 'POST', body: JSON.stringify(draft) }),
  setPromoCodeActive: (id: number, isActive: boolean) =>
    request<PromoCode>(`/pro/promo-codes/${id}`, { method: 'PATCH', body: JSON.stringify({ is_active: isActive }) }),
  proGrants: (filters: ProGrantFilters = {}, page = 1, limit = 50) =>
    request<Page<ProGrant>>(`/pro/grants?${pageParams(page, limit)}${query({ ...filters })}`),
  revokeProGrant: (id: number) => request<ProGrant>(`/pro/grants/${id}/revoke`, { method: 'POST' }),
  refundProGrant: (id: number) => request<ProGrant>(`/pro/grants/${id}/refund`, { method: 'POST' }),
  setProRenewal: (subscriptionId: number, canceled: boolean) =>
    request<ProGrant>(`/pro/subscriptions/${subscriptionId}/renewal`, {
      method: 'PUT',
      body: JSON.stringify({ canceled }),
    }),
  botQueue: () => request<BotQueue>('/bot-queue'),
  botUpdates: (view: BotUpdateView, q = '', page = 1, limit = 50) =>
    request<Page<BotUpdate>>(`/bot-queue/updates?${pageParams(page, limit)}${query({ view, q: q.trim() })}`),
  retryBotUpdate: (id: number) => request<BotUpdate>(`/bot-queue/updates/${id}/retry`, { method: 'POST' }),
  settleBotUpdate: (id: number) => request<BotUpdate>(`/bot-queue/updates/${id}/settle`, { method: 'POST' }),
  senders: () => request<SenderAccounts>('/senders'),
  /** Telegram sends a code to the number; it comes back in submitSenderCode. */
  startSenderLogin: (phone: string) =>
    request<SenderAccount>('/senders', { method: 'POST', body: JSON.stringify({ phone }) }),
  submitSenderCode: (id: number, code: string) =>
    request<SenderAccount>(`/senders/${id}/code`, { method: 'POST', body: JSON.stringify({ code }) }),
  senderLoginCode: (id: number) =>
    request<SenderLoginCode>(`/senders/${id}/login-code`, { method: 'POST', cache: 'no-store' }),
  submitSenderPassword: (id: number, password: string) =>
    request<SenderAccount>(`/senders/${id}/password`, { method: 'POST', body: JSON.stringify({ password }) }),
  setSenderEnabled: (id: number, enabled: boolean) =>
    request<SenderAccount>(`/senders/${id}/enabled`, { method: 'PUT', body: JSON.stringify({ enabled }) }),
  removeSender: (id: number) => request<void>(`/senders/${id}`, { method: 'DELETE' }),
};
