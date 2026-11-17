import type { Theme } from '@/lib/utils/themes';

/** A theme on a dot: its page and its accent, side by side. */
export default function ThemeDot({ theme, className = 'h-5 w-5 border-outline' }: { theme: Theme; className?: string }) {
  return (
    <span data-theme={theme} aria-hidden="true" className={`flex shrink-0 overflow-hidden rounded-full border-[1.5px] ${className}`}>
      <span className="flex-1 bg-background" />
      <span className="flex-1 bg-accent" />
    </span>
  );
}
