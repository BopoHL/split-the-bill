import { afterEach, describe, expect, it, vi } from 'vitest';
import { inspectTarget, sameBox } from './visibility';

const place = (element: HTMLElement, rect: { top?: number; left?: number; width?: number; height?: number }) => {
  const { top = 0, left = 0, width = 0, height = 0 } = rect;
  element.getBoundingClientRect = () => ({ top, left, width, height, bottom: top + height, right: left + width }) as DOMRect;
};

afterEach(() => {
  document.body.innerHTML = '';
  vi.restoreAllMocks();
  Reflect.deleteProperty(document, 'elementsFromPoint');
});

describe('inspectTarget', () => {
  it('waits for an element that is folded away or inert', () => {
    document.body.innerHTML = '<section inert><button id="b"></button></section><button id="z"></button>';
    const inert = document.getElementById('b')!;
    const folded = document.getElementById('z')!;
    place(inert, { top: 10, left: 10, width: 40, height: 40 });

    expect(inspectTarget(inert, null).kind).toBe('hidden');
    expect(inspectTarget(folded, null).kind).toBe('hidden');
  });

  it('asks for a scroll when the element is out of view', () => {
    document.body.innerHTML = '<button id="b"></button>';
    const button = document.getElementById('b')!;
    place(button, { top: window.innerHeight + 200, left: 10, width: 40, height: 40 });

    expect(inspectTarget(button, null).kind).toBe('below-fold');
  });

  it('waits while something else sits on top of it', () => {
    document.body.innerHTML = '<button id="b"></button><div id="sheet"></div><div id="tour"></div>';
    const button = document.getElementById('b')!;
    place(button, { top: 100, left: 10, width: 40, height: 40 });
    const tour = document.getElementById('tour')!;
    const sheet = document.getElementById('sheet')!;
    const elementsFromPoint = vi.fn(() => [tour, sheet, button]);
    Object.defineProperty(document, 'elementsFromPoint', { configurable: true, value: elementsFromPoint });

    expect(inspectTarget(button, tour).kind).toBe('covered');

    elementsFromPoint.mockReturnValue([tour, button]);
    expect(inspectTarget(button, tour)).toEqual({
      kind: 'ready',
      box: { top: 100, left: 10, width: 40, height: 40 },
    });
  });
});

describe('inspectTarget with a bar over part of the element', () => {
  it('lights only the part in the clear', () => {
    document.body.innerHTML = '<ul id="list"></ul><div id="dock"></div>';
    const list = document.getElementById('list')!;
    const dock = document.getElementById('dock')!;
    place(list, { top: 100, left: 0, width: 300, height: 600 });
    // A dock fixed over everything from 500px down.
    Object.defineProperty(document, 'elementsFromPoint', {
      configurable: true,
      value: (_x: number, y: number) => (y >= 500 ? [dock, list] : [list]),
    });

    const view = inspectTarget(list, null);

    expect(view.kind).toBe('ready');
    if (view.kind !== 'ready') return;
    expect(view.box.top).toBe(100);
    expect(view.box.top + view.box.height).toBeGreaterThan(496);
    expect(view.box.top + view.box.height).toBeLessThanOrEqual(501);
  });
});

describe('sameBox', () => {
  it('ignores sub-pixel jitter', () => {
    const box = { top: 10, left: 10, width: 40, height: 40 };
    expect(sameBox(box, { ...box, top: 10.3 })).toBe(true);
    expect(sameBox(box, { ...box, top: 12 })).toBe(false);
    expect(sameBox(null, box)).toBe(false);
  });
});
