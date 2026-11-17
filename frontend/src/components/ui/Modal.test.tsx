import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Modal from './Modal';

describe('Modal', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
    });
  });

  it('centers dialogs inside the safe viewport', () => {
    render(
      <Modal isOpen onClose={vi.fn()} title="Remove participant" size="sm">
        <p>Confirmation</p>
      </Modal>,
    );

    const dialog = screen.getByRole('dialog', { name: 'Remove participant' });
    const positioner = dialog.parentElement;

    expect(positioner?.className).toContain('items-center');
    expect(positioner?.className).toContain('justify-center');
    expect(positioner?.className).toContain('var(--content-safe-top)');
    expect(positioner?.className).toContain('var(--content-safe-right)');
    expect(positioner?.className).toContain('var(--content-safe-bottom)');
    expect(positioner?.className).toContain('var(--content-safe-left)');
    expect(positioner?.className).not.toContain('items-start');
    expect(dialog).toHaveClass('safe-modal-height');
    expect(dialog.lastElementChild?.className).toContain('min-h-0');
    expect(dialog.lastElementChild?.className).toContain('flex-1');
    expect(screen.getByRole('button', { name: 'Close' }).className).toContain('h-10');
    expect(screen.getByRole('button', { name: 'Close' }).className).toContain('w-10');
  });

  it('closes from the surrounding overlay but not from the dialog content', () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen onClose={onClose} title="Confirm">
        <button type="button">Keep open</button>
      </Modal>,
    );

    const dialog = screen.getByRole('dialog', { name: 'Confirm' });
    fireEvent.click(screen.getByRole('button', { name: 'Keep open' }));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(dialog.parentElement!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe('Modal on its way out', () => {
  it('lets presses through to what is underneath while it fades', () => {
    Object.defineProperty(window, 'scrollTo', { configurable: true, value: vi.fn() });
    const view = render(
      <Modal isOpen onClose={vi.fn()} title="Create">
        <p>Wizard</p>
      </Modal>,
    );

    view.rerender(
      <Modal isOpen={false} onClose={vi.fn()} title="Create">
        <p>Wizard</p>
      </Modal>,
    );

    const layers = [...document.querySelectorAll<HTMLElement>('.fixed.inset-0')];
    expect(layers.length).toBeGreaterThan(0);
    for (const layer of layers) expect(layer).toHaveClass('pointer-events-none');
  });
});
