import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/store/useStore', () => ({ useStore: () => ({ language: 'ru' }) }));

import UserBadge from './UserBadge';

describe('UserBadge', () => {
  it('wears its title with its own mark, in a colour of the theme', () => {
    render(<UserBadge badge="night_owl" />);

    const badge = screen.getByTitle('Сова');
    expect(badge.querySelector('svg')).not.toBeNull();
    expect(badge.style.getPropertyValue('--badge')).toBe('var(--chart-4)');
  });

  it('keeps a title it has no look for plain', () => {
    render(<UserBadge badge="someday_new" />);

    const badge = screen.getByTitle('analytics.badge.someday_new.title');
    expect(badge.querySelector('svg')).toBeNull();
    expect(badge.style.getPropertyValue('--badge')).toBe('var(--foreground)');
  });

  it('is Pro’s stamp for Pro, and nothing without a badge', () => {
    const { container } = render(<UserBadge badge={null} />);
    expect(container).toBeEmptyDOMElement();

    render(<UserBadge badge="pro" />);
    expect(screen.getByTitle('Split·Bill Pro')).toHaveTextContent('Pro');
  });
});
