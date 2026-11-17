'use client';

import { useStore } from '@/lib/store/useStore';
import { translations, Language } from './translations';

export function useTranslation() {
  const { language } = useStore();
  
  const t = (path: string, params?: Record<string, string>) => {
    const keys = path.split('.');

    const walk = (root: unknown): unknown => {
      let node = root;
      for (const key of keys) {
        if (typeof node !== 'object' || node === null) return undefined;
        node = (node as Record<string, unknown>)[key];
        if (node === undefined) return undefined;
      }
      return node;
    };

    // Resolve in the active language, falling back to English.
    let resolved = walk(translations[language as Language] || translations.en);
    if (resolved === undefined) resolved = walk(translations.en);

    if (typeof resolved !== 'string') return path;

    let result = resolved;
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        result = result.replace(`{${key}}`, value);
      });
    }

    return result;
  };

  return { t, language };
}
