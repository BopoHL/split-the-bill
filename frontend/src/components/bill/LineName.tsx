/** A receipt line's name, with «×N» when it holds several dishes. */
export default function LineName({ name, count }: { name: string; count: number }) {
  return (
    <>
      {name}
      {count > 1 && (
        <>
          {' '}
          <span className="whitespace-nowrap font-mono text-[0.92em] font-bold text-muted">×{count}</span>
        </>
      )}
    </>
  );
}
