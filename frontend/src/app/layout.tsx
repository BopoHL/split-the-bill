'use client';

import { useEffect } from 'react';
import { Caveat } from 'next/font/google';
import './globals.css';
import { useStore } from '@/lib/store/useStore';
import { initTelegramSDK, getTelegramUser, getTelegramTheme } from '@/lib/telegram/init';
import { getUserByTelegramId } from '@/lib/api/users';
import Script from 'next/script';

const caveat = Caveat({
  variable: '--font-handwritten',
  subsets: ['latin', 'cyrillic'],
  weight: ['400', '500', '600', '700'],
});

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const { theme, setTheme, setCurrentUser } = useStore();

  useEffect(() => {
    // Initialize Telegram SDK
    const webApp = initTelegramSDK();
    
    if (webApp) {
      // Set theme from Telegram
      const telegramTheme = getTelegramTheme();
      setTheme(telegramTheme);
      
      // Get and sync user with backend
      const telegramUser = getTelegramUser();
      if (telegramUser) {
        getUserByTelegramId(
          telegramUser.id,
          telegramUser.username || `${telegramUser.first_name} ${telegramUser.last_name || ''}`.trim(),
          telegramUser.photo_url
        ).then((user) => {
          if (user) {
            setCurrentUser(user);
          }
        }).catch((error) => {
          console.error('Failed to sync Telegram user in root:', error);
        });
      }
    }
  }, [setTheme, setCurrentUser]);

  // Apply theme class to html element
  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [theme]);

  return (
    <html lang="en" className={theme}>
      <head>
        <title>Split The Bill</title>
        <meta name="description" content="Split bills easily with friends in Telegram" />
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
        {/* Telegram WebApp SDK */}
        <Script 
          src="https://telegram.org/js/telegram-web-app.js" 
          strategy="beforeInteractive"
        />
      </head>
      <body className={`${caveat.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}

