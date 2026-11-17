export const AnalyticsEvent = {
  AppOpen: 'app_open',
  BillCreateOpened: 'bill_create_opened',
  BillCreateStep: 'bill_create_step',
  BillCreated: 'bill_created',
  ReceiptScanStarted: 'receipt_scan_started',
  ReceiptScanResult: 'receipt_scan_result',
  VoiceInputOpened: 'voice_input_opened',
  VoiceInputSent: 'voice_input_sent',
  VoiceInputResult: 'voice_input_result',
  ReceiptAttached: 'receipt_attached',
  ReceiptDeleted: 'receipt_deleted',
  ReceiptRated: 'receipt_rated',
  ItemsAdded: 'items_added',
  ItemUpdated: 'item_updated',
  ItemDeleted: 'item_deleted',
  ItemTaken: 'item_taken',
  ItemsAssigned: 'items_assigned',
  DishTableOpened: 'dish_table_opened',
  AmountAssigned: 'amount_assigned',
  BillTabViewed: 'bill_tab_viewed',
  BillEdited: 'bill_edited',
  BillClosed: 'bill_closed',
  BillReopened: 'bill_reopened',
  BillDeleted: 'bill_deleted',
  PayDetailsCopied: 'pay_details_copied',
  PayAmountCopied: 'pay_amount_copied',
  PaymentMarked: 'payment_marked',
  RemindersSent: 'reminders_sent',
  SeatMoved: 'seat_moved',
  SeatUserAssigned: 'seat_user_assigned',
  GuestRenamed: 'guest_renamed',
  ParticipantRemoved: 'participant_removed',
  BillLeft: 'bill_left',
  ParticipantJoined: 'participant_joined',
  ShareInvite: 'share_invite',
  InvitePromptShown: 'invite_prompt_shown',
  InvitePromptDismissed: 'invite_prompt_dismissed',
  ShareAnalytics: 'share_analytics',
  AddToHomeScreen: 'add_to_home_screen',
  LanguageChanged: 'language_changed',
  ThemeChanged: 'theme_changed',
  BadgeChosen: 'badge_chosen',
  PaymentMethodSaved: 'payment_method_saved',
  PaymentMethodDeleted: 'payment_method_deleted',
  SupportOpened: 'support_opened',
  HomeTabViewed: 'home_tab_viewed',
  AnalyticsSectionViewed: 'analytics_section_viewed',
  AnalyticsPeriodChanged: 'analytics_period_changed',
  AnalyticsPictureOpened: 'analytics_picture_opened',
  OnboardingCompleted: 'onboarding_completed',
  TourStarted: 'tour_started',
  TourStep: 'tour_step',
  TourCompleted: 'tour_completed',
  TourSkipped: 'tour_skipped',
  PaywallOpened: 'paywall_opened',
  PaywallPlanSelected: 'paywall_plan_selected',
  PaywallClosed: 'paywall_closed',
  ProCheckoutStarted: 'pro_checkout_started',
  ProCheckoutResult: 'pro_checkout_result',
  ProActivated: 'pro_activated',
  PromoRedeemed: 'promo_redeemed',
} as const;

import type { InviteChannel } from '@/lib/api/invites';
import type { StartKind } from '@/lib/utils/startParam';
import type { InvoiceStatus } from '@/lib/telegram/invoice';
import type { PaywallReason, ProPlan } from '@/types/pro';
import type { PeriodKind } from '@/types/analytics';
import type { Theme } from '@/lib/utils/themes';

type ScanMode = 'photo' | 'qr';
/** A scan makes a new bill, or adds another receipt to one. */
type ScanTarget = 'new_bill' | 'existing_bill';
type VoiceInput = 'voice' | 'text';

export interface AnalyticsEventProps {
  /** source: the channel of a `src_` link; start_ref: any other start we do not know. */
  [AnalyticsEvent.AppOpen]: { platform?: string; start: StartKind; source?: string; start_ref?: string };
  [AnalyticsEvent.BillCreateOpened]: Record<string, never>;
  [AnalyticsEvent.BillCreateStep]: { step: 'payment' } | { step: 'source'; payment_skipped: boolean };
  [AnalyticsEvent.BillCreated]: { source: 'manual' | 'voice' | ScanMode; bill_id: number };
  [AnalyticsEvent.ReceiptScanStarted]: { mode: ScanMode; target: ScanTarget };
  [AnalyticsEvent.ReceiptScanResult]: { mode: ScanMode; target: ScanTarget; ok: boolean; reason?: string };
  /** The owner opened the sheet to say the bill: from the bill, or straight after making it. */
  [AnalyticsEvent.VoiceInputOpened]: { bill_id: number; from: 'bill' | 'new_bill' };
  /** What was said went to the server: recorded, or typed where the phone can't record. */
  [AnalyticsEvent.VoiceInputSent]: { bill_id: number; input: VoiceInput };
  [AnalyticsEvent.VoiceInputResult]: { bill_id: number; input: VoiceInput; ok: boolean; reason?: string; added?: number; assigned?: number };
  /** A photo kept on the bill without being scanned. */
  [AnalyticsEvent.ReceiptAttached]: { bill_id: number };
  [AnalyticsEvent.ReceiptDeleted]: { bill_id: number; kept_items: boolean };
  /** The owner's 1–5 for how well a receipt was read. */
  [AnalyticsEvent.ReceiptRated]: { bill_id: number; rating: number };
  [AnalyticsEvent.ItemsAdded]: { bill_id: number; count: number };
  [AnalyticsEvent.ItemUpdated]: { bill_id: number };
  [AnalyticsEvent.ItemDeleted]: { bill_id: number };
  /** Someone ticked a dish as theirs on the receipt, or unticked it. */
  [AnalyticsEvent.ItemTaken]: { bill_id: number; taken: boolean };
  /** The owner handed dishes out: picked ones to people, or to one person. */
  [AnalyticsEvent.ItemsAssigned]: { bill_id: number; via: 'dishes' | 'person' | 'table'; changes: number };
  /** The owner opened the table: dishes in the middle, dragged onto the people around them. */
  [AnalyticsEvent.DishTableOpened]: { bill_id: number };
  [AnalyticsEvent.AmountAssigned]: { bill_id: number };
  [AnalyticsEvent.BillTabViewed]: { bill_id: number; tab: 'participants' | 'receipt'; role: 'owner' | 'participant' };
  [AnalyticsEvent.BillEdited]: { bill_id: number; field: 'title' | 'place' | 'headcount' | 'payment_details' };
  /** How what nobody took was handed out on closing, if anything was left. */
  [AnalyticsEvent.BillClosed]: { bill_id: number; remainder: 'none' | 'me' | 'all' };
  [AnalyticsEvent.BillReopened]: { bill_id: number };
  [AnalyticsEvent.BillDeleted]: { bill_id: number };
  [AnalyticsEvent.PayDetailsCopied]: Record<string, never>;
  [AnalyticsEvent.PayAmountCopied]: { bill_id: number };
  /** A seat marked paid or unpaid: by the owner for anyone, or by its holder,
   *  from the bill, the home list, or the button in a personal invite. */
  [AnalyticsEvent.PaymentMarked]: {
    bill_id: number;
    paid: boolean;
    by: 'owner' | 'self';
    from: 'bill' | 'home' | 'invite';
  };
  /** queued: how many reminders went out; none when nobody could be reminded. */
  [AnalyticsEvent.RemindersSent]:
    | { bill_id: number; scope: 'seat' | 'bill'; from: 'bill' | 'home'; queued: number }
    | { scope: 'all_bills'; from: 'home'; queued: number };
  /** Someone in the bill moved to another seat. */
  [AnalyticsEvent.SeatMoved]: { bill_id: number };
  /** The owner sat someone they know on a guest seat. */
  [AnalyticsEvent.SeatUserAssigned]: { bill_id: number };
  [AnalyticsEvent.GuestRenamed]: { bill_id: number };
  [AnalyticsEvent.ParticipantRemoved]: { bill_id: number };
  [AnalyticsEvent.BillLeft]: { bill_id: number };
  [AnalyticsEvent.ParticipantJoined]: {
    via: 'invite';
    /** How the invite reached them, when it was a minted one. */
    channel?: InviteChannel;
    bill_id?: number;
  };
  [AnalyticsEvent.ShareInvite]: {
    method: 'message' | 'qr';
    channel?: InviteChannel;
    bill_id?: number;
  };
  /** Asked to invite the table as a bill just made first opened; dismissed: put off. */
  [AnalyticsEvent.InvitePromptShown]: { bill_id: number };
  [AnalyticsEvent.InvitePromptDismissed]: { bill_id: number };
  [AnalyticsEvent.ShareAnalytics]: {
    picture: 'receipt' | 'bills' | 'dish' | 'person';
    method: 'message' | 'story' | 'download';
  };
  [AnalyticsEvent.AddToHomeScreen]: Record<string, never>;
  [AnalyticsEvent.LanguageChanged]: { language: string };
  [AnalyticsEvent.ThemeChanged]: { theme: Theme };
  /** null: the badge was taken off. */
  [AnalyticsEvent.BadgeChosen]: { badge: string | null };
  [AnalyticsEvent.PaymentMethodSaved]: Record<string, never>;
  [AnalyticsEvent.PaymentMethodDeleted]: Record<string, never>;
  [AnalyticsEvent.SupportOpened]: Record<string, never>;
  [AnalyticsEvent.HomeTabViewed]: { tab: 'active' | 'archive' | 'analytics' };
  /** locked: shown without Pro, behind its teaser. */
  [AnalyticsEvent.AnalyticsSectionViewed]: { section: 'overview' | 'food' | 'people' | 'places'; locked: boolean };
  [AnalyticsEvent.AnalyticsPeriodChanged]: { kind: PeriodKind };
  [AnalyticsEvent.AnalyticsPictureOpened]: { picture: 'report' | 'stories' };
  [AnalyticsEvent.TourStarted]: { source: 'first_run' | 'settings' | 'invite' | 'home'; tour: 'host' | 'guest' };
  /** The first run is behind them, with the language they chose. */
  [AnalyticsEvent.OnboardingCompleted]: { language: string };
  [AnalyticsEvent.TourStep]: { step: string };
  [AnalyticsEvent.TourCompleted]: { tour: 'host' | 'guest' };
  [AnalyticsEvent.TourSkipped]: { step: string; tour: 'host' | 'guest' };
  [AnalyticsEvent.PaywallOpened]: { reason: PaywallReason };
  [AnalyticsEvent.PaywallPlanSelected]: { plan: ProPlan };
  /** Left without buying: the cross or Escape, Telegram's back or the swipe, or «Not now». plan: the one on
   *  screen, absent while the plans have not come yet. */
  [AnalyticsEvent.PaywallClosed]: { reason: PaywallReason; via: 'close' | 'back' | 'not_now'; plan?: ProPlan; seconds: number };
  /** offer_percent: bought at the one-off discount. */
  [AnalyticsEvent.ProCheckoutStarted]: { plan: ProPlan; stars: number; reason: PaywallReason; offer_percent?: number };
  /** How Telegram's payment sheet closed; «paid» is not yet Pro, see pro_activated. */
  [AnalyticsEvent.ProCheckoutResult]: { plan: ProPlan; status: InvoiceStatus | 'unsupported' | 'error' };
  /** The app saw Pro arrive. A purchase confirmed later, or made in the bot, is
   *  recorded by the server as pro_purchased. */
  [AnalyticsEvent.ProActivated]: { via: 'stars'; plan: ProPlan } | { via: 'promo' };
  [AnalyticsEvent.PromoRedeemed]: { ok: boolean; error?: string };
}

export type AnalyticsEventName = keyof AnalyticsEventProps;
