export type ProPlan = 'month' | 'half_year' | 'year';

/** What the paywall is opened over: the thing that needs Pro, or nothing in particular. */
export type PaywallReason = 'general' | 'analytics' | 'scans' | 'reminders' | 'themes' | 'voice';

export interface ProPlanOffer {
  plan: ProPlan;
  stars: number;
  /** The struck-out price it is down from, when there is one. */
  was_stars?: number | null;
  months: number;
  /** Telegram renews it by itself every thirty days. */
  recurring: boolean;
}

export interface ProOverview {
  active: boolean;
  until: string | null;
  trial: boolean;
  subscription: boolean;
  plans: ProPlanOffer[];
  free_scans_per_day: number;
  /** Null with Pro: there is no limit to run into. */
  scans_left_today: number | null;
  free_reminders_per_month: number;
  /** «Remind everyone» presses left this month; null with Pro. */
  reminders_left_this_month: number | null;
  /** The viewer's one-off discount while it runs; the plans are already priced with it. */
  offer?: ProOffer | null;
}

export interface ProOffer {
  percent: number;
  ends_at: string;
}
