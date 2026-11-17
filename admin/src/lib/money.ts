/** Amounts arrive from the API already in currency units, never in tiins. */
export function formatMoney(amount: number, currency: string): string {
  return `${amount.toLocaleString('ru-RU')} ${currency.toUpperCase()}`;
}
