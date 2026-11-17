import type { BroadcastFormat } from './api';

/**
 * A page that shows a broadcast roughly as a chat bubble.
 *
 * Telegram's HTML is close enough to the browser's for a look before sending —
 * not a promise of the exact rendering, which is what a test send is for. An
 * ordinary message keeps its line breaks as Telegram does; a rich one flows as
 * HTML, its paragraphs and pictures in order.
 */
export function previewDocument(
  format: BroadcastFormat,
  html: string,
  { photoUrl, buttonText }: { photoUrl?: string | null; buttonText?: string | null } = {},
): string {
  const cover = format === 'message' && photoUrl ? `<img class="cover" src="${escapeAttribute(photoUrl)}" alt="">` : '';
  const button = buttonText ? `<div class="button">${escapeText(buttonText)}</div>` : '';
  return `<!doctype html><html><head><meta charset="utf-8"><style>${STYLE}</style></head><body>
<div class="bubble">${cover}<div class="${format}">${html}</div></div>${button}
</body></html>`;
}

function escapeText(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeAttribute(text: string): string {
  return escapeText(text).replace(/"/g, '&quot;');
}

const STYLE = `
:root { color-scheme: light; }
body { margin: 0; padding: 12px; background: #dbe4d0; font: 15px/1.4 -apple-system, "Segoe UI", Roboto, sans-serif; color: #111; }
.bubble { background: #fff; border-radius: 14px; padding: 8px 10px; max-width: 360px; overflow-wrap: anywhere; box-shadow: 0 1px 1px rgba(0,0,0,.12); }
.cover { display: block; width: calc(100% + 20px); margin: -8px -10px 8px; border-radius: 14px 14px 0 0; }
.message { white-space: pre-wrap; }
.rich > :first-child { margin-top: 0; }
.rich > :last-child { margin-bottom: 0; }
.rich img, .rich video { display: block; max-width: 100%; border-radius: 10px; margin: 8px 0; }
h1, h2, h3, h4, h5, h6 { margin: 10px 0 6px; line-height: 1.25; }
h1 { font-size: 22px; } h2 { font-size: 19px; } h3 { font-size: 17px; } h4, h5, h6 { font-size: 15px; }
p { margin: 6px 0; }
ul, ol { margin: 6px 0; padding-left: 22px; }
hr { border: 0; border-top: 1px solid #ddd; margin: 10px 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 14px; }
th, td { padding: 4px 6px; text-align: left; vertical-align: top; }
table[bordered] th, table[bordered] td { border: 1px solid #d5d5d5; }
table[striped] tr:nth-child(even) { background: #f3f5f7; }
blockquote, aside { margin: 6px 0; padding: 2px 10px; border-left: 3px solid #3390ec; background: #eef5fd; border-radius: 4px; }
code, pre { font-family: ui-monospace, Menlo, monospace; font-size: 13px; background: #f0f2f4; border-radius: 4px; }
code { padding: 0 3px; }
pre { padding: 6px 8px; white-space: pre-wrap; }
mark { background: #ffe98a; }
footer { color: #8a8a8a; font-size: 13px; margin-top: 6px; }
figcaption { color: #6d6d6d; font-size: 13px; }
tg-spoiler { background: #c9c9c9; color: transparent; border-radius: 3px; }
a { color: #2a7fd4; text-decoration: none; }
.button { max-width: 380px; margin-top: 4px; padding: 9px; border-radius: 10px; background: rgba(0,0,0,.18); color: #fff; text-align: center; font-weight: 600; }
`;
