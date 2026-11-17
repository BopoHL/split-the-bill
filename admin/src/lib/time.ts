/**
 * One timezone lives in this file, and nowhere else.
 *
 * Instants are stored and transported as UTC, so neither the server's own
 * timezone nor the operator's laptop clock can shift what was meant — the only
 * place a wall clock exists is the input field, and it is converted here.
 */

// Uzbekistan has been on UTC+5 without daylight saving since 1995, so a fixed
// offset is exact. Display goes through the IANA database anyway; this constant
// only has to parse what the operator typed.
const TASHKENT_UTC_OFFSET = '+05:00';
const TIME_ZONE = 'Asia/Tashkent';

/** A naive timestamp from the API means UTC — say so before the browser guesses. */
export function parseUtc(value: string): Date {
  return new Date(/(Z|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`);
}

/** `datetime-local` value (Tashkent wall clock) -> ISO instant. */
export function tashkentToUtcIso(localValue: string): string {
  return new Date(`${localValue}:00${TASHKENT_UTC_OFFSET}`).toISOString();
}

export function formatTashkent(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parseUtc(value));
}

/** The day alone, with its year: for spans that run into another year. */
export function formatTashkentDay(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(parseUtc(value));
}

/** Tashkent wall clock right now, shaped for a `datetime-local` field. */
export function tashkentNowInputValue(): string {
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
    .format(new Date())
    .replace(' ', 'T');
}
