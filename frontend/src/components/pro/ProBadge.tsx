/** «PRO» by the name of someone who has it — the app's stamp in miniature. */
export default function ProBadge({ className = '' }: { className?: string }) {
  return (
    <span
      title="Split·Bill Pro"
      className={`inline-flex h-[18px] shrink-0 items-center rounded-[4px] border-[1.5px] border-outline bg-accent px-1 font-display text-[9px] font-extrabold uppercase leading-none tracking-[0.08em] text-accent-fg ${className}`}
    >
      Pro
    </span>
  );
}
