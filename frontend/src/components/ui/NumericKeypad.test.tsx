import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en' };
  return {
    useStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  };
});

import NumericKeypad from './NumericKeypad';

const setup = (value: string, props: Partial<Parameters<typeof NumericKeypad>[0]> = {}) => {
  const onChange = vi.fn();
  render(
    <NumericKeypad open label="Amount" value={value} onChange={onChange} onClose={vi.fn()} {...props} />,
  );
  return onChange;
};

describe('NumericKeypad', () => {
  it('appends a tapped digit', () => {
    const onChange = setup('52');
    fireEvent.click(screen.getByRole('button', { name: '3' }));
    expect(onChange).toHaveBeenCalledWith('523');
  });

  it('replaces a lone leading zero', () => {
    const onChange = setup('0');
    fireEvent.click(screen.getByRole('button', { name: '7' }));
    expect(onChange).toHaveBeenCalledWith('7');
  });

  it('«000» key appends three zeros in amount mode', () => {
    const onChange = setup('52', { thousands: true });
    fireEvent.click(screen.getByRole('button', { name: '000' }));
    expect(onChange).toHaveBeenCalledWith('52000');
  });

  it('backspace drops the last digit', () => {
    const onChange = setup('523');
    fireEvent.click(screen.getByRole('button', { name: /delete/i }));
    expect(onChange).toHaveBeenCalledWith('52');
  });

  it('groups thousands in the live value', () => {
    setup('52000', { thousands: true });
    expect(screen.getByText('52 000')).toBeInTheDocument();
  });

  it('clamps a typed digit to max', () => {
    const onChange = setup('999', { max: 1000 });
    fireEvent.click(screen.getByRole('button', { name: '0' })); // 9990 → clamped
    expect(onChange).toHaveBeenCalledWith('1000');
  });

  it('keeps values within max unchanged', () => {
    const onChange = setup('5', { max: 1000 });
    fireEvent.click(screen.getByRole('button', { name: '0' }));
    expect(onChange).toHaveBeenCalledWith('50');
  });

  it('clamps the «000» key to max', () => {
    const onChange = setup('999', { thousands: true, max: 1000 });
    fireEvent.click(screen.getByRole('button', { name: '000' }));
    expect(onChange).toHaveBeenCalledWith('1000');
  });
});

describe('NumericKeypad calculator mode', () => {
  const setupCalc = (value: string) => {
    const onChange = vi.fn();
    const onClose = vi.fn();
    render(
      <NumericKeypad
        open
        label="Price"
        value={value}
        onChange={onChange}
        onClose={onClose}
        calculator
      />,
    );
    return { onChange, onClose };
  };

  it('appends an operator to the expression', () => {
    const { onChange } = setupCalc('52000');
    fireEvent.click(screen.getByRole('button', { name: '+' }));
    expect(onChange).toHaveBeenCalledWith('52000+');
  });

  it('appends a decimal point for kopecks', () => {
    const { onChange } = setupCalc('52000');
    fireEvent.click(screen.getByRole('button', { name: '.' }));
    expect(onChange).toHaveBeenCalledWith('52000.');
  });

  it('starts a negative amount with a leading minus', () => {
    const { onChange } = setupCalc('');
    fireEvent.click(screen.getByRole('button', { name: '−' }));
    expect(onChange).toHaveBeenCalledWith('-');
  });

  it('swaps a trailing operator instead of stacking', () => {
    const { onChange } = setupCalc('52000+');
    fireEvent.click(screen.getByRole('button', { name: '×' }));
    expect(onChange).toHaveBeenCalledWith('52000*');
  });

  it('replaces a lone leading zero', () => {
    const { onChange } = setupCalc('0');
    fireEvent.click(screen.getByRole('button', { name: '7' }));
    expect(onChange).toHaveBeenCalledWith('7');
  });

  it('caps a number to two decimals', () => {
    const { onChange } = setupCalc('5000.55');
    fireEvent.click(screen.getByRole('button', { name: '5' }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('shows the expression and its live total', () => {
    setupCalc('52000+3000');
    expect(screen.getByText('52 000 + 3 000')).toBeInTheDocument();
    expect(screen.getByText('55 000')).toBeInTheDocument();
  });

  it('collapses the expression to its result on Done', () => {
    const { onChange, onClose } = setupCalc('52000+3000');
    fireEvent.click(screen.getByText('Done'));
    expect(onChange).toHaveBeenCalledWith('55000');
    expect(onClose).toHaveBeenCalled();
  });

  describe('a physical keyboard', () => {
    const press = (key: string) => fireEvent.keyDown(document, { key });

    it('types a digit as if it were tapped', () => {
      const onChange = setup('52');
      press('3');
      expect(onChange).toHaveBeenCalledWith('523');
    });

    it('deletes on Backspace', () => {
      const onChange = setup('523');
      press('Backspace');
      expect(onChange).toHaveBeenCalledWith('52');
    });

    it('finishes on Enter, the same as Done', () => {
      const { onChange, onClose } = setupCalc('52000+3000');
      press('Enter');
      expect(onChange).toHaveBeenCalledWith('55000');
      expect(onClose).toHaveBeenCalled();
    });

    it('takes operators and a comma as the decimal point', () => {
      const { onChange } = setupCalc('52000');
      press('*');
      expect(onChange).toHaveBeenCalledWith('52000*');

      const second = setupCalc('52000');
      press(',');
      expect(second.onChange).toHaveBeenCalledWith('52000.');
    });

    it('keeps Escape to itself so the sheet behind the pad stays open', () => {
      // Modal closes on Escape from a document listener of its own; a pad
      // open over it used to hand the key on and lose the whole form.
      const { onClose } = setupCalc('52000');
      const sheet = vi.fn();
      document.addEventListener('keydown', sheet);
      press('Escape');
      document.removeEventListener('keydown', sheet);

      expect(onClose).toHaveBeenCalled();
      expect(sheet).not.toHaveBeenCalled();
    });

    it('ignores keys meant for a focused field', () => {
      const onChange = setup('52');
      const input = document.createElement('input');
      document.body.appendChild(input);
      fireEvent.keyDown(input, { key: '3' });
      expect(onChange).not.toHaveBeenCalled();
      input.remove();
    });

    it('leaves shortcuts alone', () => {
      const onChange = setup('52');
      fireEvent.keyDown(document, { key: '3', metaKey: true });
      expect(onChange).not.toHaveBeenCalled();
    });
  });
});

describe('NumericKeypad closing', () => {
  it('slides away instead of vanishing, and takes nothing more on its way', () => {
    const onChange = vi.fn();
    const view = render(<NumericKeypad open label="People" value="3" onChange={onChange} onClose={vi.fn()} />);

    view.rerender(<NumericKeypad open={false} label="People" value="3" onChange={onChange} onClose={vi.fn()} />);

    // Still there, sliding down — but no longer taking keys or taps.
    const sheet = screen.getByRole('button', { name: '5' }).closest('.fixed') as HTMLElement;
    expect(sheet).toHaveClass('pointer-events-none');
    fireEvent.keyDown(document, { key: '5' });
    expect(onChange).not.toHaveBeenCalled();
  });
});
