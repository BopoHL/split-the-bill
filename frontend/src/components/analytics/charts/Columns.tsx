'use client';

/**
 * A short row of columns with their values on top, the largest in the accent —
 * days of the week, parts of the day.
 */
export default function Columns({ values, labels, label, highlight }: {
  values: number[];
  labels: string[];
  /** What the chart shows, for screen readers. */
  label: string;
  highlight: number;
}) {
  const top = Math.max(...values, 1);

  return (
    <figure className="m-0" role="img" aria-label={label}>
      <div className="flex h-[110px] items-end gap-2.5 border-b-[1.5px] border-outline">
        {values.map((value, index) => (
          <div key={labels[index]} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
            <span className="font-mono text-[10px] font-bold text-foreground">{value}</span>
            <span
              className={`block w-full rounded-t-[4px] ${index === highlight ? 'bg-accent' : 'bg-foreground'}`}
              style={{ height: `${Math.round((value / top) * 84)}px` }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex gap-2.5" aria-hidden>
        {labels.map((name) => (
          <span key={name} className="min-w-0 flex-1 text-center font-mono text-[10px] text-muted">{name}</span>
        ))}
      </div>
    </figure>
  );
}
