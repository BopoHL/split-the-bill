import { describe, expect, it } from 'vitest';

import { richLength, visibleLength } from './telegramText';

describe('visibleLength', () => {
  it("doesn't charge for markup", () => {
    expect(visibleLength('<b>Привет</b>')).toBe(6);
  });

  it('counts an emoji as the two code units Telegram counts', () => {
    expect(visibleLength('\u{1F9FE}')).toBe(2);
  });

  it('leaves plain text alone', () => {
    expect(visibleLength('5 &lt; 6')).toBe(8);
  });
});

describe('richLength', () => {
  it('counts characters, so an emoji is one', () => {
    expect(richLength('<p>\u{1F680} Pro</p>')).toBe(5);
  });

  it("doesn't charge for a picture", () => {
    expect(richLength('<p>a</p><img src="https://x.uz/a.jpg"/><p>b</p>')).toBe(2);
  });
});
