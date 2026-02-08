'use client';

import { useStore } from '@/lib/store/useStore';
import { translations, Language } from './translations';

export function useTranslation() {
  const { language } = useStore();
  
  const t = (path: string, params?: Record<string, string>) => {
    const keys = path.split('.');
    let current: any = translations[language as Language] || translations.en;
    
    for (const key of keys) {
      if (current[key] === undefined) {
        // Fallback to English
        current = translations.en;
        for (const fallbackKey of keys) {
          if (current[fallbackKey] === undefined) return path;
          current = current[fallbackKey];
        }
        break;
      }
      current = current[key];
    }
    
    if (typeof current !== 'string') return path;
    
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        current = current.replace(`{${key}}`, value);
      });
    }
    
    return current;
  };

  return { t, language };
}
