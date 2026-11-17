import type { Currency } from '@/lib/utils/currency';

export type PeriodKind = 'month' | 'year' | 'all';

export type StoryKind = 'bills' | 'dish' | 'person';

export interface StoryPicture {
  story: StoryKind;
  url: string;
}

/** Signed addresses of a period's pictures, good for a day. */
export interface AnalyticsPictures {
  receipt: string;
  /** A year's stories, those it has enough in it for; none for other periods. */
  stories: StoryPicture[];
  /** What goes under a story when it is posted. */
  story_text: string | null;
}

export interface AnalyticsPeriodQuery {
  kind: PeriodKind;
  year?: number;
  month?: number;
}

export interface AnalyticsPeriod {
  kind: PeriodKind;
  year: number | null;
  month: number | null;
  first_year: number | null;
  first_month: number | null;
}

export interface BillHighlight {
  id: number;
  title: string | null;
  created_at: string;
  total: number;
  share: number;
  people: number;
}

export interface TimelinePoint {
  /** «2026-09-14» for a day of a month, «2026-09» for a month. */
  key: string;
  amount: number;
  bills: number;
}

export interface OverviewStats {
  bills: number;
  owned: number;
  joined: number;
  spent: number;
  spent_change: number | null;
  average_bill: number;
  average_share: number;
  biggest: BillHighlight | null;
  smallest: BillHighlight | null;
  collected: number;
  transferred: number;
  timeline: TimelinePoint[];
  /** Monday first. */
  weekdays: number[];
  /** Morning, day, evening, night. */
  day_parts: number[];
}

export interface Companion {
  user_id: number;
  name: string | null;
  avatar_url: string | null;
  together: number;
  invited: number;
  invited_me: number;
  paid_me: number;
  paid_them: number;
}

export interface PaySpeed {
  user_id: number;
  name: string | null;
  minutes: number;
  payments: number;
}

export interface PeopleStats {
  companions: Companion[];
  speed: PaySpeed[];
  distinct: number;
}

export type DishGroup = 'food' | 'drink' | 'dessert' | 'alcohol' | 'fee' | 'discount' | 'other';

export interface GroupShare {
  group: DishGroup;
  amount: number;
}

export interface DishCount {
  kind: string | null;
  name: string;
  count: number;
}

export interface Champion {
  kind: string;
  name: string;
  often: string;
  often_count: number;
  priciest: string;
  priciest_price: number;
}

export interface PriceRise {
  dish: string;
  place: string;
  first_price: number;
  last_price: number;
  change: number;
  since: string;
}

export interface FoodStats {
  groups: GroupShare[];
  top: DishCount[];
  champions: Champion[];
  price_rises: PriceRise[];
  fees: number;
  labeled: number;
}

export interface PlaceStat {
  id: number;
  name: string;
  visits: number;
  spent: number;
  average_bill: number;
  last_visit: string;
}

export interface PlacesStats {
  top: PlaceStat[];
  new: string[];
  unplaced: number;
}

export type BadgeKey = 'coffee_lover' | 'meat_lover' | 'regular' | 'night_owl' | 'treasurer' | 'social' | 'fast_payer';

export interface Badge {
  key: BadgeKey;
  value: number;
  subject: string | null;
}

export interface Analytics {
  period: AnalyticsPeriod;
  /** Without Pro only the top of the overview is filled in. */
  locked: boolean;
  currency: Currency;
  other_currency_bills: number;
  overview: OverviewStats;
  people: PeopleStats;
  food: FoodStats;
  places: PlacesStats;
  badges: Badge[];
}
