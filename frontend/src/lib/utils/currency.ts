export const CURRENCY_SYMBOL = 'сўм';

/**
 * Convert display format to currency amount (e.g., 1250 -> "1,250 сўм")
 */
export function formatCurrency(amount: number): string {
  // Use regex to add spaces as thousands separator
  // We first convert to string with fixed decimals if needed, or just as is
  // But for split-the-bill usually we don't have many decimals, or we have 2
  const parts = amount.toString().split('.');
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return `${parts.join('.')} ${CURRENCY_SYMBOL}`;
}

/**
 * Convert display format to amount (e.g., "1.250,50" or "1250.50" -> 1250.50)
 */
export function displayToAmount(display: string | number): number {
  if (typeof display === 'number') return display;
  const cleanStr = display.replace(/,/g, '.').replace(/[^\d.-]/g, '');
  const num = parseFloat(cleanStr);
  return isNaN(num) ? 0 : num;
}

/**
 * Split amount evenly among participants
 * Remainder goes to the first participant (creator)
 */
export function splitEvenly(totalSum: number, participantCount: number): number[] {
  if (participantCount === 0) return [];
  
  const baseAmount = Math.floor(totalSum / participantCount);
  const remainder = totalSum % participantCount;
  
  const amounts = new Array(participantCount).fill(baseAmount);
  
  // Add remainder to first participant (creator)
  if (remainder > 0) {
    amounts[0] += remainder;
  }
  
  return amounts;
}

/**
 * Validate that amounts sum to total
 */
export function validateSplit(amounts: number[], total: number): boolean {
  const sum = amounts.reduce((acc, amount) => acc + amount, 0);
  return sum === total;
}

/**
 * Calculate remaining unallocated amount
 */
export function calculateRemaining(total: number, allocated: number[]): number {
  const sum = allocated.reduce((acc, amount) => acc + amount, 0);
  return total - sum;
}
