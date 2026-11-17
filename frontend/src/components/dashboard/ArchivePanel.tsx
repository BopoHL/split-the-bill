'use client';

import { Receipt, Search } from 'lucide-react';
import type { BillRoleFilter } from '@/lib/api/bills';
import type { Archive } from '@/hooks/useArchive';
import Button from '@/components/ui/Button';
import { formatTotals, groupByMonth, monthLabel, totalsByCurrency } from '@/lib/utils/home';
import { billUnit } from '@/lib/utils/plural';
import { useTranslation } from '@/lib/i18n/useTranslation';
import ArchiveRow from './ArchiveRow';
import { RowsCard } from './RowParts';

// The server reads no more of a search than this.
const SEARCH_MAX_LENGTH = 100;

/** The closed bills: searched, split by who ran them, gathered by month. */
export default function ArchivePanel({ archive, userId, onDelete }: {
  archive: Archive;
  userId: number;
  onDelete: (billId: number) => Promise<void>;
}) {
  const { t, language } = useTranslation();
  const groups = groupByMonth(archive.bills, !archive.hasMore);
  const filters: Array<{ role: BillRoleFilter | undefined; label: string; count: number | undefined }> = [
    { role: undefined, label: t('home.filterAll'), count: archive.counts?.all },
    { role: 'owner', label: t('home.filterOwned'), count: archive.counts?.owned },
    { role: 'participant', label: t('home.filterJoined'), count: archive.counts?.joined },
  ];

  if (!archive.loading && !archive.failed && archive.total === 0) {
    return (
      <div className="rounded-[10px] border-[1.5px] border-dashed border-outline bg-surface px-6 py-8 text-center">
        <Receipt className="mx-auto mb-3 h-7 w-7 text-muted-2" />
        <p className="text-pretty font-display text-[15px] font-bold text-foreground">{t('home.noHistory')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <label className="flex h-12 items-center gap-2.5 rounded-lg border-[1.5px] border-outline bg-surface px-3.5 text-muted">
        <Search className="h-[18px] w-[18px] shrink-0" />
        <input
          type="search"
          value={archive.query}
          onChange={(event) => archive.setQuery(event.target.value)}
          aria-label={t('home.searchLabel')}
          placeholder={t('home.searchPlaceholder')}
          maxLength={SEARCH_MAX_LENGTH}
          className="h-11 min-w-0 flex-1 bg-transparent text-[15px] text-foreground outline-none placeholder:text-muted"
        />
      </label>

      <div className="mt-3 flex flex-wrap gap-2">
        {filters.map((filter) => {
          const selected = archive.role === filter.role;
          return (
            <button
              key={filter.label}
              type="button"
              aria-pressed={selected}
              onClick={() => archive.setRole(filter.role)}
              className={`flex min-h-11 items-center gap-1.5 rounded-full border-[1.5px] border-outline px-3.5 font-display text-[13px] font-bold transition-colors ${
                selected ? 'bg-emphasis text-emphasis-fg' : 'bg-transparent text-foreground hover:bg-surface'
              }`}
            >
              {filter.label}
              {filter.count !== undefined && (
                <span className={`font-mono text-[11px] font-medium ${selected ? '' : 'text-muted'}`}>{filter.count}</span>
              )}
            </button>
          );
        })}
      </div>

      {groups.map((group) => {
        const summary = `${group.bills.length} ${billUnit(group.bills.length, language)} · ${formatTotals(
          totalsByCurrency(group.bills, (bill) => bill.total_sum),
        )}`;
        return (
          <section key={group.key} className="mt-5">
            <div className="mb-2 flex items-baseline justify-between gap-3 px-0.5">
              <h3 className="font-mono text-[11px] font-bold uppercase tracking-[0.08em] text-muted">
                {monthLabel(group.month, language)}
              </h3>
              {group.complete && <span className="truncate font-mono text-[11px] text-muted">{summary}</span>}
            </div>
            <RowsCard quiet>
              {group.bills.map((bill) => (
                <ArchiveRow key={bill.id} bill={bill} userId={userId} onDelete={onDelete} />
              ))}
            </RowsCard>
          </section>
        );
      })}

      {archive.failed && (
        <div className="mt-5 rounded-[10px] border-[1.5px] border-dashed border-outline bg-surface px-5 py-6 text-center">
          <p className="font-display text-[15px] font-bold text-foreground">{t('home.archiveFailed')}</p>
          <Button variant="outline" onClick={archive.retry} className="mt-3 rounded-full">
            {t('errors.retry')}
          </Button>
        </div>
      )}

      {!archive.loading && !archive.failed && archive.bills.length === 0 && archive.narrowed && (
        <div className="mt-5 rounded-[10px] border-[1.5px] border-dashed border-outline bg-surface px-5 py-7 text-center">
          <p className="font-display text-[15px] font-bold text-foreground">{t('home.nothingFound')}</p>
          <p className="mt-1.5 text-[13px] text-muted">{t('home.nothingFoundHint')}</p>
        </div>
      )}

      {archive.hasMore && (
        <div className="mt-6 flex justify-center">
          <Button variant="outline" onClick={() => void archive.loadMore()} disabled={archive.loadingMore} className="rounded-full">
            {archive.loadingMore ? t('home.loadingMore') : t('home.loadMore')}
          </Button>
        </div>
      )}
    </div>
  );
}
