import { describe, expect, it } from 'vitest';

import { previewDocument } from './broadcastPreview';

describe('previewDocument', () => {
  it('keeps the line breaks of an ordinary message and puts its photo on top', () => {
    const page = previewDocument('message', '<b>Новое</b>\nстрока', { photoUrl: 'blob:cover' });

    expect(page).toContain('<img class="cover" src="blob:cover"');
    expect(page).toContain('<div class="message"><b>Новое</b>\nстрока</div>');
    expect(page.indexOf('class="cover"')).toBeLessThan(page.indexOf('class="message"'));
  });

  it('flows a rich message as HTML, with no photo but its own pictures', () => {
    const html = '<p>До</p><img src="https://x.uz/compare.jpg"/><p>После</p>';
    const page = previewDocument('rich', html, { photoUrl: 'blob:ignored' });

    expect(page).toContain(`<div class="rich">${html}</div>`);
    expect(page).not.toContain('blob:ignored');
  });

  it('draws the button under the bubble, its label as text', () => {
    const page = previewDocument('rich', '<p>x</p>', { buttonText: '⭐ PRO <b>' });

    expect(page).toContain('<div class="button">⭐ PRO &lt;b&gt;</div>');
  });
});
