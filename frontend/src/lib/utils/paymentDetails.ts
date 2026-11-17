/** Longest card number there is, in digits. */
const CARD_DIGITS = 19;

/**
 * Payment details as they are typed: a card number in groups of four, or a
 * phone number with its «+»; anything but digits is dropped.
 */
export function formatDetails(input: string): string {
  const phone = input.trimStart().startsWith('+');
  const digits = input.replace(/\D/g, '');
  if (phone) return `+${digits}`;
  return digits.slice(0, CARD_DIGITS).replace(/(\d{4})(?=\d)/g, '$1 ');
}

const digitsOf = (details: string) => details.replace(/[\s-]/g, '');

/** The same details however they were spaced: saved ones and the bill's may differ. */
export function sameDetails(a: string, b: string): boolean {
  return a.trim() !== '' && digitsOf(a) === digitsOf(b);
}

export type CardBrand = 'UZCARD' | 'HUMO' | 'VISA' | 'MASTERCARD' | 'MIR';

/** The card's payment system, told by its first digits once there are four. */
export function cardBrand(details: string): CardBrand | null {
  const digits = digitsOf(details);
  if (!/^\d{4,}$/.test(digits)) return null;
  const head = Number(digits.slice(0, 4));
  if (head === 8600) return 'UZCARD';
  if (head === 9860) return 'HUMO';
  if (digits.startsWith('4')) return 'VISA';
  if ((head >= 5100 && head <= 5599) || (head >= 2221 && head <= 2720)) return 'MASTERCARD';
  if (head >= 2200 && head <= 2204) return 'MIR';
  return null;
}

/** A card number in groups of four however it was saved; other details as they are. */
export function displayDetails(details: string): string {
  const digits = digitsOf(details);
  return /^\d{12,19}$/.test(digits) ? formatDetails(digits) : details;
}
