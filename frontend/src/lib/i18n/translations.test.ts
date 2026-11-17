import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { translations } from './translations';

const LANGS = ['en', 'ru', 'uz'] as const;

function flatten(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([key, value]) =>
    typeof value === 'object' && value !== null
      ? flatten(value as Record<string, unknown>, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );
}

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    if (!/\.tsx?$/.test(entry.name)) return [];
    if (entry.name.startsWith('translations')) return [];
    return [full];
  });
}

describe('translations', () => {
  it('keeps the three languages in step', () => {
    const [en, ru, uz] = LANGS.map((lang) => new Set(flatten(translations[lang])));
    expect([...ru].filter((k) => !en.has(k))).toEqual([]);
    expect([...en].filter((k) => !ru.has(k))).toEqual([]);
    expect([...en].filter((k) => !uz.has(k))).toEqual([]);
  });

  it('has every key the app asks for', () => {
    // A miss is silent at runtime — `t` returns the path, so the user just sees
    // «bill.somethingSomething» on screen.
    const known = new Set(flatten(translations.en));
    const missing = new Set<string>();

    for (const file of sourceFiles(path.join(process.cwd(), 'src'))) {
      const text = fs.readFileSync(file, 'utf8');
      for (const [, key] of text.matchAll(/\bt\(\s*'([a-zA-Z]+\.[a-zA-Z0-9_]+)'/g)) {
        if (!known.has(key)) missing.add(`${key} (${path.basename(file)})`);
      }
    }

    expect([...missing]).toEqual([]);
  });
});
