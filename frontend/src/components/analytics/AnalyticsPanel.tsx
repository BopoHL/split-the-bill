'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { Lock, ReceiptText, Sparkles, type LucideIcon } from 'lucide-react';
import type { Analytics, AnalyticsPeriodQuery } from '@/types/analytics';
import { getAnalytics } from '@/lib/api/analytics';
import { createSessionCache } from '@/lib/cache/sessionCache';
import { currentPeriod } from '@/lib/utils/analytics';
import { useTranslation } from '@/lib/i18n/useTranslation';
import PeriodBar from './PeriodBar';
import OverviewSection from './OverviewSection';
import FoodSection from './FoodSection';
import PeopleSection from './PeopleSection';
import PlacesSection from './PlacesSection';
import ReportSheet from './ReportSheet';
import YearStories from './YearStories';
import Locked from './Locked';
import { usePro } from '@/lib/store/usePro';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { Empty } from './parts';

const SECTIONS = ['overview', 'food', 'people', 'places'] as const;
const SHARE_CHIP =
  'inline-flex min-h-11 items-center gap-1.5 rounded-full border-[1.5px] bg-surface px-3.5 font-display text-[13px] font-bold';
type Section = (typeof SECTIONS)[number];
/** What each section holds, said over its lock without Pro. */
const LOCKED_ITEMS: Record<Exclude<Section, 'overview'>, string[]> = {
  food: ['groups', 'champions', 'top', 'prices'],
  people: ['company', 'invites', 'speed', 'balance'],
  places: ['favourites', 'fresh'],
};

const seenAnswers = createSessionCache<Analytics>();
const answerKey = (userId: number, period: AnalyticsPeriodQuery) =>
  `${userId}:${period.kind}:${period.year ?? ''}:${period.month ?? ''}`;

/**
 * The person's bills seen from above, a section at a time, for a month, a year
 * or all time. Nothing is asked for until the tab is first opened.
 */
export default function AnalyticsPanel({ userId, active }: { userId: number; active: boolean }) {
  const { t } = useTranslation();
  const [section, setSection] = useState<Section>('overview');
  const [period, setPeriod] = useState<AnalyticsPeriodQuery>(() => currentPeriod('month'));
  const key = answerKey(userId, period);
  // Every period seen this session: going back to one shows it at once, and
  // it is asked for again quietly in case anything changed since.
  const [answers, setAnswers] = useState(() => new Map(seenAnswers.entries()));
  const [failedKey, setFailedKey] = useState<string | null>(null);
  // While a new period is on its way the last one stays up, dimmed.
  const [shownKey, setShownKey] = useState<string | null>(null);
  const [opened, setOpened] = useState(active);
  const [sheet, setSheet] = useState<'report' | 'stories' | null>(null);
  const openPaywall = usePro((state) => state.openPaywall);

  if (active && !opened) setOpened(true);
  if (answers.has(key) && shownKey !== key) setShownKey(key);

  useEffect(() => {
    if (!opened) return;
    let current = true;
    const asked = answerKey(userId, period);
    getAnalytics(userId, period)
      .then((data) => {
        if (!current) return;
        seenAnswers.set(asked, data);
        setAnswers((known) => new Map(known).set(asked, data));
      })
      .catch((error) => {
        console.error('Error loading analytics:', error);
        if (current) setFailedKey(asked);
      });
    return () => {
      current = false;
    };
  }, [opened, userId, period]);

  const data = answers.get(key) ?? (shownKey ? answers.get(shownKey) : undefined) ?? null;
  // The pictures are drawn for one period: another one starts them afresh.
  const periodKey = `${period.kind}-${period.year ?? ''}-${period.month ?? ''}`;
  const loading = !answers.has(key);
  const failed = loading && failedKey === key;

  const locked = (name: Exclude<Section, 'overview'>) => (
    <Locked title={t(`analytics.locked.${name}`)} items={LOCKED_ITEMS[name].map((item) => t(`analytics.lockedItem.${item}`))} />
  );
  const sections: Record<Section, (analytics: Analytics) => ReactNode> = {
    overview: (analytics) => <OverviewSection data={analytics} />,
    food: (analytics) => (analytics.locked ? locked('food') : <FoodSection data={analytics} />),
    people: (analytics) => (analytics.locked ? locked('people') : <PeopleSection data={analytics} />),
    places: (analytics) => (analytics.locked ? locked('places') : <PlacesSection data={analytics} />),
  };
  // Without Pro the pictures are behind the paywall too.
  const open = (picture: 'report' | 'stories') => {
    if (data?.locked) {
      openPaywall('analytics');
      return;
    }
    setSheet(picture);
    track(AnalyticsEvent.AnalyticsPictureOpened, { picture });
  };
  const showSection = (name: Section) => {
    setSection(name);
    track(AnalyticsEvent.AnalyticsSectionViewed, { section: name, locked: !!data?.locked });
  };
  const changePeriod = (next: AnalyticsPeriodQuery) => {
    setPeriod(next);
    track(AnalyticsEvent.AnalyticsPeriodChanged, { kind: next.kind });
  };
  const pictureIcon = (Icon: LucideIcon) => (data?.locked ? <Lock className="h-4 w-4" /> : <Icon className="h-4 w-4" />);

  return (
    <div className="flex flex-col gap-3.5">
      <nav aria-label={t('analytics.sections')} className="flex gap-1 overflow-x-auto border-b-[1.5px] border-border">
        {SECTIONS.map((name) => (
          <button
            key={name}
            type="button"
            aria-current={section === name ? 'page' : undefined}
            onClick={() => showSection(name)}
            className={`-mb-[1.5px] min-h-11 shrink-0 border-b-[3px] px-3 font-display text-[14px] transition-colors ${
              section === name ? 'border-accent font-extrabold text-foreground' : 'border-transparent font-bold text-muted'
            }`}
          >
            {t(`analytics.${name}`)}
          </button>
        ))}
      </nav>

      <PeriodBar period={period} known={data?.period ?? null} onChange={changePeriod} />

      {!loading && data && data.overview.bills > 0 && (
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => open('report')} className={`${SHARE_CHIP} border-outline text-foreground`}>
            {pictureIcon(ReceiptText)}
            {t('analytics.reportButton')}
          </button>
          {period.kind === 'year' && (
            <button type="button" onClick={() => open('stories')} className={`${SHARE_CHIP} border-accent text-accent`}>
              {pictureIcon(Sparkles)}
              {t('analytics.yearStories')}
            </button>
          )}
        </div>
      )}

      {failed ? (
        <Empty title={t('common.error')} />
      ) : !data ? (
        <div className="flex justify-center py-16">
          <div className="h-10 w-10 animate-spin rounded-full border-b-2 border-accent" />
        </div>
      ) : data.overview.bills === 0 ? (
        <Empty title={t('analytics.empty')} hint={t('analytics.emptyHint')} />
      ) : (
        <div className={`transition-opacity ${loading ? 'opacity-50' : ''}`} aria-busy={loading}>
          {sections[section](data)}
        </div>
      )}

      <ReportSheet key={`report-${periodKey}`} userId={userId} period={period} open={sheet === 'report'} onClose={() => setSheet(null)} />
      {period.kind === 'year' && period.year && (
        <YearStories key={`stories-${periodKey}`} userId={userId} year={period.year} open={sheet === 'stories'} onClose={() => setSheet(null)} />
      )}
    </div>
  );
}
