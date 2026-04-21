"use client";

import { useEffect } from "react";
import i18n from "i18next";

import { initI18n, normalizeLanguage, type AppLanguage } from "./init";

export function I18nProvider({
  language,
  children,
}: {
  language: AppLanguage | string;
  children: React.ReactNode;
}) {
  useEffect(() => {
    initI18n();
    const nextLang = normalizeLanguage(language);
    if (i18n.language !== nextLang) {
      void i18n.changeLanguage(nextLang);
    }

    // Keep <html lang="..."> in sync for accessibility & Intl defaults
    if (typeof document !== "undefined") {
      document.documentElement.lang = nextLang;
    }
  }, [language]);

  return children;
}
