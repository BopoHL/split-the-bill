'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { BroadcastFormat } from '@/lib/api';
import { previewDocument } from '@/lib/broadcastPreview';

interface Props {
  format: BroadcastFormat;
  body: Record<string, string>;
  languages: readonly string[];
  photo: File | null;
  buttonText: string | null;
}

/**
 * How the draft will look, one language at a time.
 *
 * The page sits in a sandbox with scripts off: it is the operator's own HTML,
 * but nothing in it should be able to act inside the panel.
 */
export default function BroadcastPreview({ format, body, languages, photo, buttonText }: Props) {
  const [language, setLanguage] = useState(languages[0]);
  const [height, setHeight] = useState(160);
  const frame = useRef<HTMLIFrameElement>(null);
  const photoUrl = useObjectUrl(format === 'message' ? photo : null);

  const page = useMemo(
    () => previewDocument(format, body[language] ?? '', { photoUrl, buttonText }),
    [format, body, language, photoUrl, buttonText],
  );

  const fitToContent = () => {
    // Nothing to measure until the page has a layout (it has none in tests).
    const measured = frame.current?.contentDocument?.documentElement.scrollHeight;
    if (measured) setHeight(measured);
  };

  return (
    <div className="mb-4">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted">Превью</span>
        <span className="flex gap-1" role="tablist" aria-label="Язык превью">
          {languages.map((lang) => (
            <button
              key={lang}
              type="button"
              role="tab"
              aria-selected={lang === language}
              onClick={() => setLanguage(lang)}
              className={`rounded px-2 py-0.5 text-xs uppercase transition-colors ${
                lang === language ? 'bg-foreground text-background' : 'text-muted hover:text-foreground'
              }`}
            >
              {lang}
            </button>
          ))}
        </span>
      </div>
      <iframe
        ref={frame}
        title="Превью рассылки"
        sandbox="allow-same-origin"
        srcDoc={page}
        onLoad={fitToContent}
        style={{ height }}
        className="w-full rounded-md border border-border"
      />
    </div>
  );
}

function useObjectUrl(file: File | null): string | null {
  const url = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  return url;
}
