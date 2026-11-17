import type { Metadata, Viewport } from 'next';
import { Manrope, Onest, JetBrains_Mono } from 'next/font/google';
import Script from 'next/script';
import './globals.css';
import AppShell from '@/components/layout/AppShell';

// Redesign «Bold» type. Cyrillic-capable stand-ins for the mock's Latin-only
// Space Grotesk / Instrument Sans; JetBrains Mono for numbers/amounts.
const fontDisplay = Manrope({
  variable: '--ff-display',
  subsets: ['latin', 'cyrillic'],
  weight: ['500', '600', '700'],
  display: 'swap',
});
const fontBody = Onest({
  variable: '--ff-body',
  subsets: ['latin', 'cyrillic'],
  weight: ['400', '500', '600'],
  display: 'swap',
});
const fontMono = JetBrains_Mono({
  variable: '--ff-mono',
  subsets: ['latin', 'cyrillic'],
  weight: ['400', '500', '700'],
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Split The Bill',
  description: 'Split bills easily with friends in Telegram',
};

// Single source of truth for the viewport. `viewport-fit=cover` lets the app
// paint under the notch — the safe-area insets are re-applied by SafeAreaProvider.
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: 'cover',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <Script src="https://telegram.org/js/telegram-web-app.js" strategy="beforeInteractive" />
      </head>
      <body className={`${fontDisplay.variable} ${fontBody.variable} ${fontMono.variable} antialiased`}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
