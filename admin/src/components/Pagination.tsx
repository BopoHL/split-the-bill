'use client';

interface PaginationProps {
  page: number;
  limit: number;
  total: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ page, limit, total, onPageChange }: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const current = Math.min(page, pageCount);
  const start = total === 0 ? 0 : (current - 1) * limit + 1;
  const end = Math.min(total, current * limit);
  const pages = pageWindow(current, pageCount);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface px-3 py-2 text-sm">
      <div className="text-muted">
        {start}-{end} из <span className="tabular-nums">{total}</span>
      </div>
      <div className="flex items-center gap-1">
        <PageButton
          label="Назад"
          disabled={current <= 1}
          onClick={() => onPageChange(current - 1)}
        />
        {pages.map((item, index) =>
          item === 'gap' ? (
            <span key={`gap-${index}`} className="px-2 text-muted">
              ...
            </span>
          ) : (
            <button
              key={item}
              onClick={() => onPageChange(item)}
              className={`min-h-10 min-w-10 rounded-md px-3 text-sm font-medium tabular-nums transition-colors ${
                item === current
                  ? 'bg-foreground text-background'
                  : 'text-muted hover:bg-background hover:text-foreground'
              }`}
              aria-current={item === current ? 'page' : undefined}
            >
              {item}
            </button>
          ),
        )}
        <PageButton
          label="Вперёд"
          disabled={current >= pageCount}
          onClick={() => onPageChange(current + 1)}
        />
      </div>
    </div>
  );
}

function PageButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="min-h-10 rounded-md px-3 text-sm font-medium text-muted transition-colors hover:bg-background hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
    >
      {label}
    </button>
  );
}

function pageWindow(current: number, pageCount: number): Array<number | 'gap'> {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, index) => index + 1);

  const middleStart = Math.max(2, current - 1);
  const middleEnd = Math.min(pageCount - 1, current + 1);
  const pages: Array<number | 'gap'> = [1];

  if (middleStart > 2) pages.push('gap');
  for (let value = middleStart; value <= middleEnd; value += 1) pages.push(value);
  if (middleEnd < pageCount - 1) pages.push('gap');
  pages.push(pageCount);

  return pages;
}
