"use client";

import { motion } from "framer-motion";
import { useTranslation } from "@/lib/i18n/useTranslation";
import TelegramLoginButton from "./TelegramLoginButton";
import { useStore } from "@/lib/store/useStore";
import { getUserByTelegramId } from "@/lib/api/users";

interface TelegramAuthUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

export default function ExternalLanding() {
  const { t } = useTranslation();
  const { setCurrentUser } = useStore();
  const botUsername =
    process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || "SplitTheBillsBot";
  const cleanUsername = botUsername.startsWith('@') ? botUsername.slice(1) : botUsername;
  
  const handleTelegramAuth = async (user: TelegramAuthUser) => {
    try {
      const syncedUser = await getUserByTelegramId(
        user.id,
        user.username || `${user.first_name} ${user.last_name || ''}`.trim(),
        user.photo_url,
        undefined, // no initData for widget
        user       // send full widget user object for hash verification
      );
      if (syncedUser) {
        setCurrentUser(syncedUser);
      }
    } catch (error) {
      console.error('Failed to sync external user:', error);
    }
  };

  return (
    <div className="min-h-screen notebook-page flex items-center justify-center p-4">
      <motion.div
        className="max-w-md w-full bg-paper/90 backdrop-blur-md p-8 rounded-2xl border-2 border-dashed border-accent/40 shadow-xl transform rotate-1"
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
      >
        <div className="text-center space-y-6">
          <div className="flex justify-center">
            <div className="w-20 h-20 bg-paper-highlight border-2 border-ink rounded-full flex items-center justify-center shadow-inner transform -rotate-3">
              <span className="text-5xl">💰</span>
            </div>
          </div>

          <h1 className="text-4xl font-handwritten text-ink font-bold">
            {t('landing.title')}
          </h1>

          <p className="text-xl font-handwritten text-ink/80 leading-relaxed">
            {t('common.openInTelegram').split('Telegram').map((part, i, arr) => (
              <span key={i}>
                {part}
                {i < arr.length - 1 && <span className="text-accent font-bold">Telegram</span>}
              </span>
            ))}
          </p>

          <div className="pt-4 flex justify-center">
            <TelegramLoginButton 
              botName={cleanUsername}
              onAuth={handleTelegramAuth}
            />
          </div>

          <p className="text-sm font-handwritten text-ink/60 italic transform -rotate-1">
            &quot;{t('common.tagline')}&quot;
          </p>
        </div>
      </motion.div>

      {/* Decorative notebook elements */}
      <div className="fixed top-12 left-0 w-full h-[2px] bg-accent/10 pointer-events-none" />
      <div className="fixed top-24 left-0 w-full h-[2px] bg-accent/10 pointer-events-none" />
      <div className="fixed top-36 left-0 w-full h-[2px] bg-accent/10 pointer-events-none" />
    </div>
  );
}
