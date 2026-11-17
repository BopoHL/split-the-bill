import type { NextConfig } from 'next';

/**
 * The panel is a plain SPA that talks to the same API as the mini app, so it is
 * exported as static files and served by the existing nginx. That keeps a second
 * Node process off the 2 GB VPS entirely.
 */
const nextConfig: NextConfig = {
  output: 'export',
  images: { unoptimized: true },
};

export default nextConfig;
