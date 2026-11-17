import type { ButtonHTMLAttributes } from 'react';
import type { LucideIcon } from 'lucide-react';

export type ChipTone = 'default' | 'accent' | 'success' | 'danger';

const TONES: Record<ChipTone, string> = {
  default: 'border-outline bg-surface text-foreground',
  accent: 'border-outline bg-accent text-accent-fg',
  success: 'border-outline bg-success text-success-fg',
  danger: 'border-danger bg-surface text-danger',
};

interface ChipButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: LucideIcon;
  tone?: ChipTone;
}

/**
 * The compact «Bold» action used inside rows: ink outline, small hard shadow,
 * sinks on press. Without a label it becomes a square icon button, which then
 * needs an aria-label.
 */
export default function ChipButton({
  icon: Icon,
  tone = 'default',
  type = 'button',
  className = '',
  children,
  ...props
}: ChipButtonProps) {
  return (
    <button
      type={type}
      className={`btn-hard-sm inline-flex min-h-9 min-w-9 max-w-full items-center justify-center gap-1.5 rounded-[5px] border-[1.5px] font-display text-[12px] font-bold leading-[1.15] break-words disabled:cursor-not-allowed disabled:opacity-40 ${
        children ? 'px-2.5 py-1.5 text-left' : 'px-0'
      } ${TONES[tone]} ${className}`}
      {...props}
    >
      {Icon && <Icon className="h-3.5 w-3.5 flex-shrink-0" strokeWidth={2.25} />}
      {children}
    </button>
  );
}
