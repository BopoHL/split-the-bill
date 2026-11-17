import { describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useDishSelection } from './useDishSelection';

describe('useDishSelection', () => {
  it('picks a whole group, then drops it once all of it is picked', () => {
    const { result } = renderHook(() => useDishSelection());

    act(() => result.current.toggle(['1:0']));
    act(() => result.current.toggle(['1:0', '1:1']));
    expect([...result.current.keys]).toEqual(['1:0', '1:1']);

    act(() => result.current.toggle(['1:0', '1:1']));
    expect(result.current.keys.size).toBe(0);
  });

  it('forgets what was picked when picking ends', () => {
    const { result } = renderHook(() => useDishSelection());

    act(() => result.current.start());
    act(() => result.current.add(['2:0', '3:0']));
    expect(result.current.active).toBe(true);

    act(() => result.current.stop());
    expect(result.current.active).toBe(false);
    expect(result.current.keys.size).toBe(0);
  });
});
