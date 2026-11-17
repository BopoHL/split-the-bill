'use client';

import { useState } from 'react';

interface ReceiptThumbProps {
  src?: string | null;
  index: number;
  scanning?: boolean;
}

/**
 * The little slip next to a receipt row.
 *
 * The drawn version is not just a placeholder: a Soliq import has no photo at
 * all, and photos are purged after a while to keep the disk in check, so a
 * receipt without an image is a normal state rather than a broken one.
 */
export default function ReceiptThumb({ src, index, scanning }: ReceiptThumbProps) {
  const [failed, setFailed] = useState(false);
  const showPhoto = !!src && !failed;

  return (
    <span className="relative flex h-16 w-16 flex-shrink-0 overflow-hidden rounded-[7px] border-[1.5px] border-outline bg-white">
      {showPhoto ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt=""
          onError={() => setFailed(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        <span
          aria-hidden
          className={`flex h-full w-full flex-col gap-[3px] p-2 ${scanning ? 'opacity-30' : ''}`}
        >
          <span className="h-[4px] w-[54%] rounded-[1px] bg-[#3a352c]" />
          <span className="h-[3px] w-full rounded-[2px] bg-[#d9d2c4]" />
          <span className="h-[3px] w-[78%] rounded-[2px] bg-[#d9d2c4]" />
          <span className="h-[3px] w-[52%] rounded-[2px] bg-[#d9d2c4]" />
        </span>
      )}

      <span className="absolute left-1 top-1 flex h-[19px] w-[19px] items-center justify-center rounded-[5px] border-[1.5px] border-outline bg-accent font-display text-[10px] font-extrabold text-accent-fg">
        {index}
      </span>

      {scanning && (
        <span className="absolute inset-0 flex items-center justify-center bg-surface/75">
          <span className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        </span>
      )}
    </span>
  );
}
