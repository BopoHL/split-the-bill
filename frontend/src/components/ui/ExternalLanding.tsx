"use client";

import { motion } from "framer-motion";
import { Receipt } from "lucide-react";
import { useTranslation } from "@/lib/i18n/useTranslation";

// Outside Telegram there is no signed init data, and every API call needs it,
// so the page only points people to Telegram.
export default function ExternalLanding() {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <motion.div
        className="w-full max-w-md overflow-hidden rounded-[10px] border-[1.5px] border-outline bg-surface shadow-[var(--shadow-lifted)]"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
      >
        {/* Ink header with logo + wordmark */}
        <div className="bg-bar px-6 py-[22px] text-center">
          <div className="mx-auto mb-3.5 flex h-[60px] w-[60px] items-center justify-center rounded-[12px] border-[1.5px] border-bar-fg bg-white/5 text-accent">
            <Receipt className="h-[30px] w-[30px]" />
          </div>
          <h1 className="font-display text-[26px] font-bold tracking-[0.01em] text-bar-fg">
            {t('landing.title')}
          </h1>
        </div>

        {/* Body */}
        <div className="px-6 pb-7 pt-6 text-center">
          <p className="text-[15px] font-medium leading-relaxed text-muted">
            {t('common.openInTelegram')
              .split('Telegram')
              .map((part, i, arr) => (
                <span key={i}>
                  {part}
                  {i < arr.length - 1 && (
                    <span className="font-bold text-accent">Telegram</span>
                  )}
                </span>
              ))}
          </p>

          <div className="mt-[18px] font-mono text-[11px] tracking-[0.02em] text-muted-2">
            {'// '}
            {t('common.tagline')}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
