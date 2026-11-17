'use client';

import { useEffect, useState } from 'react';
import { api, type ScanDetail as Detail } from '@/lib/api';
import { formatTashkent } from '@/lib/time';

interface Props {
  id: number;
  onClose: () => void;
}

/**
 * Everything that went into one parsed receipt, side by side: the photo, the
 * text OCR read off it, and the JSON the model answered with. Comparing the
 * three is the only way to tell whose fault a wrong bill was.
 */
export default function ScanDetail({ id, onClose }: Props) {
  const [scan, setScan] = useState<Detail | null>(null);

  useEffect(() => {
    api.scan(id).then(setScan).catch(console.error);
  }, [id]);

  if (!scan) return <p className="py-10 text-center text-muted">Загрузка…</p>;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <button
          onClick={onClose}
          className="rounded-md border border-border px-2.5 py-1 text-sm text-muted transition-colors hover:text-foreground"
        >
          ← Назад
        </button>
        <h2 className="text-lg font-bold">
          Скан #{scan.id} · {scan.bill_title ?? 'без названия'}
        </h2>
        <span className="rounded-md bg-surface px-2 py-0.5 text-xs text-muted">{scan.status}</span>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border border-border bg-surface p-4 text-sm md:grid-cols-6">
        <Fact label="Источник" value={scan.source} />
        <Fact label="Модель" value={scan.llm_model ?? '—'} />
        <Fact label="Пользователь" value={scan.user ? `@${scan.user}` : '—'} />
        <Fact label="Оценка" value={scan.scan_quality ? `${scan.scan_quality} из 5` : 'нет'} />
        <Fact label="Позиций" value={String(scan.items_count)} />
        <Fact
          label="Итог счёта"
          value={scan.bill_total === null ? '—' : formatAmount(scan.bill_total)}
        />
        <Fact label="Когда" value={formatTashkent(scan.created_at)} />
      </dl>

      {scan.error_message && (
        <p className="rounded-lg border border-danger px-4 py-3 text-sm text-danger">
          {scan.error_message}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-3">
          {scan.has_photo ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={api.scanPhotoUrl(scan.id)}
              alt={`Чек скана ${scan.id}`}
              className="w-full rounded-lg border border-border"
            />
          ) : (
            <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              {scan.source_url ? 'QR-импорт, фотографии нет' : 'Фотография не сохранилась'}
            </p>
          )}
          {scan.source_url && (
            <p className="break-all text-xs text-muted-2">{scan.source_url}</p>
          )}
        </div>

        <div className="space-y-4">
          <Block title="Позиции счёта">
            {scan.items.length === 0 ? (
              <p className="text-sm text-muted">Позиций нет</p>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {scan.items.map((item, index) => (
                    <tr key={index} className="border-t border-border first:border-t-0">
                      <td className="py-1.5 pr-3">
                        {item.name}
                        {item.is_shared_globally && (
                          <span className="ml-1.5 text-xs text-muted-2">на всех</span>
                        )}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums text-muted">
                        ×{item.count}
                      </td>
                      <td className="py-1.5 text-right tabular-nums">
                        {formatAmount(item.item_sum)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Block>

          <Block title="Сырой текст OCR">
            <Raw value={scan.ocr_text} />
          </Block>

          <Block title="Ответ модели">
            <Raw value={scan.llm_response} />
          </Block>
        </div>
      </div>
    </div>
  );
}

/** Every amount in the scan API is in tiins; it is turned into money here. */
function formatAmount(tiins: number): string {
  return (tiins / 100).toLocaleString('ru-RU');
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">{title}</div>
      {children}
    </div>
  );
}

function Raw({ value }: { value: string | null }) {
  if (!value) return <p className="text-sm text-muted">Пусто</p>;
  return (
    <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
      {value}
    </pre>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-muted">{label}</dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  );
}
