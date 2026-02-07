'use client';

import { useEffect } from 'react';
import { Caveat } from 'next/font/google';
import './globals.css';
import { useStore } from '@/lib/store/useStore';
import { initTelegramSDK, getTelegramUser, getTelegramTheme } from '@/lib/telegram/init';
import { createOrUpdateUser } from '@/lib/api/users';

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
      
      // Get and create/update user
      const telegramUser = getTelegramUser();
      if (telegramUser) {
        createOrUpdateUser({
          telegram_id: telegramUser.id,
          username: telegramUser.username || `${telegramUser.first_name} ${telegramUser.last_name || ''}`.trim(),
          avatar_url: telegramUser.photo_url,
        }).then((user) => {
          setCurrentUser(user);
        }).catch((error) => {
          console.error('Failed to create/update user:', error);
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
      </head>
      <body className={`${caveat.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}

