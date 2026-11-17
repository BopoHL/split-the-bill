import { useEffect, useState } from 'react';
import { getAppConfig } from '@/lib/api/appConfig';

// Asked once per launch: every settings menu on every screen wants it, and it
// only changes when an operator changes it.
let pending: Promise<string | null> | null = null;

function supportUsername(): Promise<string | null> {
  pending ??= getAppConfig()
    .then((config) => config.support_username)
    .catch(() => {
      pending = null;
      return null;
    });
  return pending;
}

/** Whom «Contact support» opens a chat with; null until known, or when the app could not ask. */
export function useSupportUsername(): string | null {
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    void supportUsername().then((name) => {
      if (current) setUsername(name);
    });
    return () => {
      current = false;
    };
  }, []);

  return username;
}
