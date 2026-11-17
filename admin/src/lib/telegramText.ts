/**
 * The length Telegram will count.
 *
 * Markup doesn't take up room in the limit, and the unit is UTF-16 code units —
 * which is what a JavaScript string already measures in, so an emoji counts as
 * two here without any help.
 */
export function visibleLength(body: string): number {
  return body.replace(/<[^>]*>/g, '').length;
}

/**
 * The length Telegram counts for a rich message: markup is free here too, but
 * the unit is a character, so an emoji counts as one.
 */
export function richLength(body: string): number {
  return [...body.replace(/<[^>]*>/g, '')].length;
}
