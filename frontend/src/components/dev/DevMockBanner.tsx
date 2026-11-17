'use client';

/**
 * Dev-only banner showing the active mock Telegram user and links to
 * switch between presets. Rendered only when the dev mock is enabled.
 *
 * The whole module is dynamic-imported from layout.tsx behind the
 * `process.env.NODE_ENV !== 'production'` check, so it never ends up in
 * the prod bundle.
 */
import { useState } from 'react';
import { MOCK_USERS, resolveMockUser, type MockUserKey } from '@/lib/telegram/devMock';

export default function DevMockBanner() {
  // This component is dynamic-imported with `ssr: false`, so `window`
  // is guaranteed to exist here — safe to resolve the active user
  // during initial render instead of via a setState-in-effect.
  const [active] = useState<MockUserKey>(() => resolveMockUser().key);

  const switchTo = (key: MockUserKey) => {
    const url = new URL(window.location.href);
    url.searchParams.set('mockUser', key);
    // full reload so the SDK re-installs with the new identity
    window.location.assign(url.toString());
  };

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 8,
        right: 8,
        zIndex: 9999,
        fontFamily: 'ui-monospace, monospace',
        fontSize: 11,
        background: 'rgba(0,0,0,0.78)',
        color: '#fff',
        padding: '6px 10px',
        borderRadius: 6,
        boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
        pointerEvents: 'auto',
        userSelect: 'none',
      }}
    >
      <div style={{ opacity: 0.7, marginBottom: 2 }}>DEV MOCK</div>
      <div>
        {(Object.keys(MOCK_USERS) as MockUserKey[]).map((key, i) => (
          <span key={key}>
            {i > 0 && <span style={{ opacity: 0.4 }}> · </span>}
            <button
              onClick={() => switchTo(key)}
              style={{
                background: 'none',
                border: 'none',
                color: key === active ? '#fcc419' : '#fff',
                fontWeight: key === active ? 700 : 400,
                textDecoration: key === active ? 'none' : 'underline',
                cursor: 'pointer',
                padding: 0,
                font: 'inherit',
              }}
            >
              {MOCK_USERS[key].first_name}
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}
