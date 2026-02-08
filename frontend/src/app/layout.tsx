'use client';

import { useEffect, useState } from 'react';
import { Caveat } from 'next/font/google';
import './globals.css';
import { useStore } from '@/lib/store/useStore';
import { initTelegramSDK, getTelegramUser, getTelegramTheme, isTelegramWebApp } from '@/lib/telegram/init';
import { getUserByTelegramId } from '@/lib/api/users';
import Script from 'next/script';
import ExternalLanding from '@/components/ui/ExternalLanding';

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
  const { theme, setTheme, setCurrentUser, language } = useStore();
  const [isTelegram, setIsTelegram] = useState<boolean | null>(null);

  useEffect(() => {
    // Check if running in Telegram
    const isTG = isTelegramWebApp();
    setIsTelegram(isTG);

    if (isTG) {
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
            telegramUser.photo_url,
            window.Telegram?.WebApp?.initData
          ).then((user) => {
            if (user) {
              setCurrentUser(user);
            }
          }).catch((error) => {
            console.error('Failed to sync Telegram user in root:', error);
          });
        }
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

  // Use translations for head metadata
  const title = language === 'ru' ? 'Разделяй Счет' : language === 'uz' ? 'Hisobni Bo\'lish' : 'Split The Bill';
  const description = language === 'ru' ? 'Легко делите счета с друзьями в Telegram' : language === 'uz' ? 'Telegram-da do\'stlar bilan hisob-kitoblarni osongina bo\'lishing' : 'Split bills easily with friends in Telegram';

  return (
    <html lang={language} className={theme}>
      <head>
        <title>{title}</title>
        <meta name="description" content={description} />
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
        {/* Telegram WebApp SDK */}
        <Script 
          src="https://telegram.org/js/telegram-web-app.js" 
          strategy="beforeInteractive"
        />
      </head>
      <body className={`${caveat.variable} antialiased`}>
        {isTelegram === null ? (
          <div className="min-h-screen notebook-page flex items-center justify-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent"></div>
          </div>
        ) : isTelegram === false ? (
          <ExternalLanding />
        ) : (
          children
        )}
      </body>
    </html>
  );
}

