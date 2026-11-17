'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  api,
  type BillDetail as Detail,
  type BillItem,
  type BillParticipant,
  type ReceiptSummary,
} from '@/lib/api';
import { formatMoney } from '@/lib/money';
import { formatTashkent } from '@/lib/time';

interface Props {
  id: number;
  onClose: () => void;
  onOpenUser: (id: number) => void;
}

export default function BillDetail({ id, onClose, onOpenUser }: Props) {
  const [bill, setBill] = useState<Detail | null>(null);

  useEffect(() => {
    api.bill(id).then(setBill).catch(console.error);
  }, [id]);

  const participantNames = useMemo(() => {
    const names = new Map<number, string>();
    for (const participant of bill?.participants ?? []) {
      names.set(participant.id, participantLabel(participant));
    }
    return names;
  }, [bill]);

  if (!bill) return <p className="py-10 text-center text-muted">Загрузка…</p>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={onClose}
          className="min-h-10 rounded-md border border-border px-3 text-sm text-muted transition-colors hover:text-foreground"
        >
          ← Назад
        </button>
        <h2 className="text-lg font-bold">
          {bill.title || `Счёт #${bill.id}`}
          <span className="ml-2 text-sm font-normal text-muted-2">#{bill.id}</span>
        </h2>
        <span className="rounded-md bg-surface px-2 py-0.5 text-xs text-muted">
          {bill.is_deleted ? 'удалён' : statusLabel(bill.status)}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border border-border bg-surface p-4 text-sm md:grid-cols-6">
        <Fact label="Владелец">
          <UserLink id={bill.owner_id} label={bill.owner || `#${bill.owner_id}`} onOpen={onOpenUser} />
        </Fact>
        <Fact label="Итог" value={formatMoney(bill.total_sum, bill.currency)} />
        <Fact label="Распределено" value={formatMoney(bill.allocated_sum, bill.currency)} />
        <Fact label="Не распределено" value={formatMoney(bill.unallocated_sum, bill.currency)} />
        <Fact label="Оплатили" value={`${bill.paid_count} из ${bill.participants.length}`} />
        <Fact label="Создан" value={formatTashkent(bill.created_at)} />
      </dl>

      {bill.scan_total_mismatch && (
        <p className="rounded-lg border border-danger px-4 py-3 text-sm text-danger">
          Сумма позиций не совпадает с итогом распознанных чеков.
        </p>
      )}

      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <section className="space-y-3">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted">Чеки</h3>
          {bill.receipts.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              Чеков нет
            </p>
          ) : (
            bill.receipts.map((receipt) => (
              <ReceiptCard key={receipt.task_id} billId={bill.id} receipt={receipt} currency={bill.currency} />
            ))
          )}
        </section>

        <section className="space-y-4">
          <Block title="Позиции и распределение">
            {bill.items.length === 0 ? (
              <p className="text-sm text-muted">Позиций нет</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase tracking-wider text-muted">
                    <tr>
                      <th className="py-2 pr-3">Позиция</th>
                      <th className="py-2 pr-3 text-right">Кол-во</th>
                      <th className="py-2 pr-3">Кому</th>
                      <th className="py-2 text-right">Сумма</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bill.items.map((item) => (
                      <tr key={item.id} className="border-t border-border">
                        <td className="py-2 pr-3">
                          <div className="font-medium">{item.name}</div>
                          {item.receipt_task_id && (
                            <div className="text-xs text-muted-2">чек #{item.receipt_task_id}</div>
                          )}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums text-muted">×{item.count}</td>
                        <td className="py-2 pr-3 text-muted">
                          {itemSplitLabel(item, participantNames)}
                        </td>
                        <td className="py-2 text-right tabular-nums">
                          {formatMoney(item.item_sum, bill.currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Block>

          <Block title="Оплаты участников">
            {bill.participants.length === 0 ? (
              <p className="text-sm text-muted">Участников нет</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase tracking-wider text-muted">
                    <tr>
                      <th className="py-2 pr-3">Участник</th>
                      <th className="py-2 pr-3 text-right">Доля</th>
                      <th className="py-2">Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bill.participants.map((participant) => (
                      <tr key={participant.id} className="border-t border-border">
                        <td className="py-2 pr-3">
                          {participant.user_id ? (
                            <UserLink
                              id={participant.user_id}
                              label={participantLabel(participant)}
                              onOpen={onOpenUser}
                            />
                          ) : (
                            <span>{participantLabel(participant)}</span>
                          )}
                          <div className="text-xs text-muted-2">место {participant.seat_index + 1}</div>
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {formatMoney(participant.allocated_amount, bill.currency)}
                        </td>
                        <td className="py-2">
                          {participant.is_paid ? (
                            <span className="text-success">оплачено</span>
                          ) : (
                            <span className="text-muted">ожидает</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Block>
        </section>
      </div>
    </div>
  );
}

function ReceiptCard({
  billId,
  receipt,
  currency,
}: {
  billId: number;
  receipt: ReceiptSummary;
  currency: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <div className="font-medium">
            Чек {receipt.index}
            {receipt.merchant_name && <span className="ml-1 text-muted">· {receipt.merchant_name}</span>}
          </div>
          <div className="text-xs text-muted-2">
            {receipt.source} · {receipt.status} · {formatTashkent(receipt.created_at)}
          </div>
        </div>
        <div className="text-right text-sm tabular-nums">
          {receipt.total === null ? '—' : formatMoney(receipt.total, currency)}
          <div className="text-xs text-muted-2">{receipt.items_count} поз.</div>
        </div>
      </div>
      {receipt.has_photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={api.billReceiptPhotoUrl(billId, receipt.task_id)}
          alt={`Чек ${receipt.index}`}
          className="mt-2 w-full rounded-md"
          style={{ outline: '1px solid rgba(0, 0, 0, 0.1)' }}
        />
      ) : (
        <p className="rounded-md border border-dashed border-border px-3 py-5 text-center text-xs text-muted">
          Фото нет
        </p>
      )}
      {receipt.quality && (
        <div className="mt-2 text-xs text-muted">Оценка скана: {receipt.quality} из 5</div>
      )}
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">{title}</div>
      {children}
    </div>
  );
}

function Fact({
  label,
  value,
  children,
}: {
  label: string;
  value?: string;
  children?: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-muted">{label}</dt>
      <dd className="mt-0.5">{children ?? value}</dd>
    </div>
  );
}

function UserLink({ id, label, onOpen }: { id: number; label: string; onOpen: (id: number) => void }) {
  return (
    <button
      onClick={() => onOpen(id)}
      className="inline-flex min-h-10 items-center text-left font-medium transition-colors hover:text-accent"
    >
      {label}
    </button>
  );
}

function participantLabel(participant: BillParticipant): string {
  if (participant.username) return participant.username;
  const fullName = [participant.name, participant.surname].filter(Boolean).join(' ');
  if (fullName) return fullName;
  if (participant.guest_name) return participant.guest_name;
  return participant.is_guest ? `Гость ${participant.seat_index + 1}` : `#${participant.id}`;
}

function itemSplitLabel(item: BillItem, participantNames: Map<number, string>): string {
  if (item.is_shared_globally) return 'на всех участников';
  if (item.portions.length <= 1) {
    return assigneesLabel(item.portions[0] ?? item.assigned_participant_ids, participantNames);
  }
  return item.portions
    .map((ids, index) => `${index + 1}: ${assigneesLabel(ids, participantNames)}`)
    .join(' · ');
}

function assigneesLabel(ids: number[], participantNames: Map<number, string>): string {
  if (ids.length === 0) return 'не распределено';
  return ids.map((id) => participantNames.get(id) ?? `место #${id}`).join(', ');
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    open: 'открыт',
    paid: 'оплачен',
    closed: 'закрыт',
  };
  return labels[status] ?? status;
}
