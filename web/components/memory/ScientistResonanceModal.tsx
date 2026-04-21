"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCw, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

import Modal from "@/components/common/Modal";
import {
  buildScientistLoadingSequence,
  getLoadingCopyForLanguage,
} from "@/lib/scientist-resonance-loading.js";
import {
  getScientistResonance,
  regenerateScientistResonance,
  type ScientistResonanceCard,
  type ScientistResonanceLongTermResult,
  type ScientistResonanceResponse,
} from "@/lib/personalization-api";

interface ScientistResonanceModalProps {
  isOpen: boolean;
  language: string;
  onClose: () => void;
}

const EMPTY_PAYLOAD: ScientistResonanceResponse = {
  long_term: null,
  recent_state: null,
};

type ResonanceTab = "long_term" | "recent_state";
const LOADING_COPY_ROTATION_MS = 2400;

function isChineseLanguage(language: string) {
  return String(language || "").toLowerCase().startsWith("zh");
}

function getDisplayQuote(card: ScientistResonanceCard, language: string) {
  if (isChineseLanguage(language)) {
    return card.quote_zh || card.quote_en;
  }
  return card.quote_en || card.quote_zh;
}

function getDisplayBio(card: ScientistResonanceCard, language: string) {
  if (isChineseLanguage(language)) {
    return card.bio_zh || card.bio_en;
  }
  return card.bio_en || card.bio_zh;
}

function getDisplayAchievements(card: ScientistResonanceCard, language: string) {
  const zhItems = card.achievements_zh ?? [];
  const enItems = card.achievements_en ?? [];
  return isChineseLanguage(language) ? (zhItems.length ? zhItems : enItems) : (enItems.length ? enItems : zhItems);
}

function getDisplayLoadingCopy(card: ScientistResonanceCard, language: string) {
  if (isChineseLanguage(language)) {
    return card.loading_copy_zh || card.loading_copy_en;
  }
  return card.loading_copy_en || card.loading_copy_zh;
}

function ScientistHoverCard({
  card,
  language,
  dossierLabel,
  achievementsLabel,
}: {
  card: ScientistResonanceCard;
  language: string;
  dossierLabel: string;
  achievementsLabel: string;
}) {
  const bio = getDisplayBio(card, language);
  const achievements = getDisplayAchievements(card, language);

  return (
    <div className="pointer-events-none absolute right-3 top-3 z-20 hidden w-[280px] rounded-[22px] border border-[rgba(176,80,30,0.16)] bg-[rgba(255,252,247,0.96)] p-4 opacity-0 shadow-[0_18px_44px_rgba(37,29,21,0.14)] backdrop-blur-sm transition duration-200 md:block group-hover/card:translate-y-0 group-hover/card:opacity-100">
      <p className="text-[10px] uppercase tracking-[0.18em] text-[var(--primary)]">{dossierLabel}</p>
      <h4 className="mt-2 font-serif text-[24px] leading-none tracking-[-0.02em] text-[var(--foreground)]">
        {card.name}
      </h4>
      {bio ? <p className="mt-3 text-[12px] leading-6 text-[var(--muted-foreground)]">{bio}</p> : null}
      {achievements.length > 0 ? (
        <div className="mt-4 rounded-[16px] border border-[var(--border)]/65 bg-[var(--background)]/78 p-3">
          <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--muted-foreground)]">{achievementsLabel}</p>
          <ul className="mt-2 space-y-1.5">
            {achievements.map((item) => (
              <li key={item} className="text-[12px] leading-5 text-[var(--foreground)]">
                · {item}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function CardView({
  card,
  language,
  cardLabel,
  whyLabel,
  confidenceLabel,
  dossierLabel,
  achievementsLabel,
}: {
  card: ScientistResonanceCard;
  language: string;
  cardLabel: string;
  whyLabel: string;
  confidenceLabel: string;
  dossierLabel: string;
  achievementsLabel: string;
}) {
  const displayQuote = getDisplayQuote(card, language);
  const displayHook = isChineseLanguage(language) ? card.hook : "";

  return (
    <div className="group/card relative overflow-hidden rounded-[28px] border border-[var(--border)]/70 bg-[var(--card)] shadow-[0_20px_60px_rgba(37,29,21,0.07)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(176,80,30,0.10),transparent_34%),linear-gradient(135deg,rgba(236,231,221,0.46),transparent_48%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(176,80,30,0.45),transparent)]" />
      <ScientistHoverCard
        card={card}
        language={language}
        dossierLabel={dossierLabel}
        achievementsLabel={achievementsLabel}
      />

      <div className="relative grid gap-4 p-4 md:grid-cols-[156px_minmax(0,1fr)] md:p-5">
        <div className="relative">
          <div className="absolute inset-x-3 -top-2.5 z-10 rounded-full border border-[var(--border)]/60 bg-[var(--background)]/90 px-3 py-1 text-center text-[9px] uppercase tracking-[0.22em] text-[var(--muted-foreground)] backdrop-blur">
            {cardLabel}
          </div>
          <div className="relative overflow-hidden rounded-[22px] border border-[var(--border)]/70 bg-[linear-gradient(180deg,rgba(236,231,221,0.95),rgba(250,249,246,0.6))] p-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
            <div className="relative overflow-hidden rounded-[16px] border border-[var(--border)]/70 bg-[#d9d2c7]">
              <div className="pointer-events-none absolute inset-0 z-10 bg-[linear-gradient(180deg,transparent,rgba(0,0,0,0.16))]" />
              <Image
                src={card.portrait_url}
                alt={card.name}
                width={512}
                height={512}
                className="h-[198px] w-full object-cover grayscale transition-transform duration-700 hover:scale-[1.03] md:h-[218px]"
                priority={false}
              />
            </div>
            <div className="mt-2.5 flex items-center justify-between gap-3 px-1">
              <div className="min-w-0">
                <p className="font-serif text-[15px] leading-none tracking-[0.02em] text-[var(--foreground)]">
                  {card.name}
                </p>
                <p className="mt-1 text-[9px] uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
                  {confidenceLabel}
                </p>
              </div>
              <div className="h-7 w-7 rounded-full border border-[var(--border)]/70 bg-[var(--background)]/90 shadow-sm" />
            </div>
          </div>
        </div>

        <div className="relative min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[9px] uppercase tracking-[0.24em] text-[var(--muted-foreground)]">
                {cardLabel}
              </p>
              <h3 className="mt-2.5 max-w-2xl font-serif text-[28px] leading-[0.98] tracking-[-0.03em] text-[var(--foreground)] md:text-[34px]">
                {card.name}
              </h3>
            </div>
            <div className="rounded-full border border-[rgba(176,80,30,0.18)] bg-[rgba(176,80,30,0.08)] px-2.5 py-1 text-[9px] uppercase tracking-[0.18em] text-[var(--primary)]">
              {confidenceLabel}
            </div>
          </div>

          {displayHook ? (
            <p className="mt-3 max-w-2xl font-serif text-[15px] italic leading-6 text-[var(--muted-foreground)] md:text-[16px]">
              {displayHook}
            </p>
          ) : null}

          <div className="mt-4 rounded-[20px] border border-[var(--border)]/70 bg-[linear-gradient(135deg,rgba(236,231,221,0.68),rgba(255,255,255,0.72))] px-4 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
            <div className="mb-3 h-px w-10 bg-[var(--primary)]/45" />
            <p className="max-w-2xl font-serif text-[18px] leading-7 tracking-[-0.01em] text-[var(--foreground)] md:text-[19px]">
              “{displayQuote}”
            </p>
          </div>

          <div className="mt-4 rounded-[20px] border border-[var(--border)]/70 bg-[var(--background)]/85 px-4 py-3.5">
            <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              {whyLabel}
            </p>
            <p className="mt-2.5 max-w-2xl text-[13px] leading-6 text-[var(--foreground)]">
              {card.reason}
            </p>
          </div>

          {card.resonance_axes.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {card.resonance_axes.slice(0, 4).map((axis) => (
                <span
                  key={axis}
                  className="rounded-full border border-[var(--border)]/70 bg-[var(--card)] px-3 py-1 text-[10px] uppercase tracking-[0.1em] text-[var(--muted-foreground)] shadow-[0_6px_18px_rgba(37,29,21,0.04)]"
                >
                  {axis}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function SecondaryCard({
  card,
  language,
  title,
  dossierLabel,
  achievementsLabel,
}: {
  card: ScientistResonanceCard;
  language: string;
  title: string;
  dossierLabel: string;
  achievementsLabel: string;
}) {
  return (
    <div className="group/card relative overflow-hidden rounded-[22px] border border-[var(--border)]/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(236,231,221,0.58))] p-3 shadow-[0_14px_34px_rgba(37,29,21,0.06)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(176,80,30,0.10),transparent_36%)]" />
      <ScientistHoverCard
        card={card}
        language={language}
        dossierLabel={dossierLabel}
        achievementsLabel={achievementsLabel}
      />
      <div className="relative">
        <p className="text-[9px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">{title}</p>
        <div className="mt-2.5 grid grid-cols-[72px_minmax(0,1fr)] gap-3">
          <div className="overflow-hidden rounded-[16px] border border-[var(--border)]/70 bg-[#d9d2c7]">
            <Image
              src={card.portrait_url}
              alt={card.name}
              width={256}
              height={256}
              className="h-[94px] w-full object-cover grayscale"
            />
          </div>
          <div className="min-w-0">
            <h4 className="font-serif text-[19px] leading-none tracking-[-0.02em] text-[var(--foreground)]">
              {card.name}
            </h4>
            <p className="mt-2 line-clamp-2 text-[12px] leading-5 text-[var(--muted-foreground)]">
              {card.reason}
            </p>
            {card.resonance_axes.length > 0 ? (
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {card.resonance_axes.slice(0, 2).map((axis) => (
                  <span
                    key={axis}
                    className="rounded-full border border-[var(--border)]/65 bg-[var(--background)]/85 px-2 py-1 text-[9px] uppercase tracking-[0.08em] text-[var(--muted-foreground)]"
                  >
                    {axis}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ScientistResonanceModal({
  isOpen,
  language,
  onClose,
}: ScientistResonanceModalProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<ResonanceTab>("long_term");
  const [payload, setPayload] = useState<ScientistResonanceResponse>(EMPTY_PAYLOAD);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await getScientistResonance(language);
      setPayload(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Unknown error"));
    } finally {
      setLoading(false);
    }
  }, [language, t]);

  useEffect(() => {
    if (!isOpen) return;
    void load();
  }, [isOpen, load]);

  useEffect(() => {
    if (!isOpen) {
      setActiveTab("long_term");
      setError("");
    }
  }, [isOpen]);

  const currentView = useMemo(
    () => (activeTab === "long_term" ? payload.long_term : payload.recent_state),
    [activeTab, payload.long_term, payload.recent_state],
  );

  const longTerm = activeTab === "long_term" ? (currentView as ScientistResonanceLongTermResult | null) : null;
  const currentCard = activeTab === "recent_state" ? (currentView as ScientistResonanceCard | null) : longTerm?.primary ?? null;
  const loadingCards = useMemo(() => {
    return buildScientistLoadingSequence(payload);
  }, [payload]);
  const activeLoadingCopy = loadingCards.length
    ? getLoadingCopyForLanguage(loadingCards[loadingMessageIndex % loadingCards.length]!, language)
    : "";

  const handleRegenerate = useCallback(async () => {
    setRefreshing(true);
    setError("");
    try {
      const next = await regenerateScientistResonance(language, activeTab);
      setPayload(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Unknown error"));
    } finally {
      setRefreshing(false);
    }
  }, [activeTab, language, t]);

  useEffect(() => {
    if (!refreshing || loadingCards.length <= 1) {
      return;
    }
    const interval = window.setInterval(() => {
      setLoadingMessageIndex((prev) => (prev + 1) % loadingCards.length);
    }, LOADING_COPY_ROTATION_MS);
    return () => window.clearInterval(interval);
  }, [loadingCards.length, refreshing]);

  useEffect(() => {
    if (!refreshing) {
      return;
    }
    setLoadingMessageIndex(0);
  }, [loadingCards.length, refreshing]);

  const footer = (
    <div className="flex items-center justify-end gap-2">
      <button
        type="button"
        onClick={onClose}
        className="rounded-xl border border-[var(--border)]/70 px-3.5 py-2 text-[13px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--foreground)]/25 hover:text-[var(--foreground)]"
      >
        {t("scientist_resonance.modal.close")}
      </button>
      <button
        type="button"
        onClick={() => void handleRegenerate()}
        disabled={refreshing || loading}
        className="inline-flex items-center gap-2 rounded-xl bg-[var(--primary)] px-3.5 py-2 text-[13px] font-medium text-[var(--primary-foreground)] shadow-[0_14px_28px_rgba(176,80,30,0.22)] transition-transform transition-opacity hover:-translate-y-[1px] disabled:translate-y-0 disabled:opacity-50"
      >
        {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        {t("scientist_resonance.modal.regenerate")}
      </button>
    </div>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={refreshing ? () => undefined : onClose}
      title={t("scientist_resonance.modal.title")}
      titleIcon={<Sparkles className="h-4 w-4" />}
      width="xl"
      footer={footer}
      closeOnBackdrop={!refreshing}
    >
      <div className="bg-[linear-gradient(180deg,rgba(250,249,246,0.85),transparent_24%)] px-4 py-3">
        <div className="relative overflow-hidden rounded-[24px] border border-[var(--border)]/70 bg-[linear-gradient(135deg,rgba(255,255,255,0.96),rgba(236,231,221,0.75))] px-4 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
          <div className="pointer-events-none absolute right-[-4rem] top-[-4rem] h-28 w-28 rounded-full bg-[rgba(176,80,30,0.10)] blur-3xl" />
          <div className="relative flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div className="max-w-lg">
              <p className="text-[11px] uppercase tracking-[0.28em] text-[var(--primary)]">
                {t("scientist_resonance.modal.kicker")}
              </p>
              <p className="mt-2 max-w-lg text-[13px] leading-6 text-[var(--muted-foreground)]">
                {t("scientist_resonance.modal.subtitle")}
              </p>
            </div>

            <div className="inline-flex rounded-2xl border border-[var(--border)]/70 bg-[var(--background)]/80 p-1 shadow-sm backdrop-blur">
              {([
                ["long_term", t("scientist_resonance.tab.long_term")],
                ["recent_state", t("scientist_resonance.tab.recent_state")],
              ] as const).map(([tab, label]) => {
                const active = activeTab === tab;
                return (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={`rounded-xl px-3 py-1.5 text-[11px] transition-all ${
                      active
                        ? "bg-[var(--foreground)] text-[var(--background)] shadow-[0_10px_20px_rgba(31,29,27,0.12)]"
                        : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {error ? <p className="mt-4 text-[12px] text-red-500">{error}</p> : null}

        <div className="relative mt-4">
          {loading ? (
            <div className="flex min-h-[340px] items-center justify-center rounded-[24px] border border-[var(--border)]/70 bg-[var(--muted)]/25">
              <Loader2 className="h-5 w-5 animate-spin text-[var(--primary)]" />
            </div>
          ) : currentCard ? (
            <div className="space-y-3">
              <CardView
                card={currentCard}
                language={language}
                cardLabel={t("scientist_resonance.card.label")}
                whyLabel={t("scientist_resonance.card.why")}
                dossierLabel={t("scientist_resonance.hover.dossier")}
                achievementsLabel={t("scientist_resonance.hover.achievements")}
                confidenceLabel={
                  currentCard.confidence_style === "strong_resonance"
                    ? t("scientist_resonance.card.confidence.strong")
                    : t("scientist_resonance.card.confidence.phase")
                }
              />
              {activeTab === "long_term" && longTerm && longTerm.secondary.length > 0 ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {longTerm.secondary.map((card, index) => (
                    <SecondaryCard
                      key={card.slug}
                      card={card}
                      language={language}
                      title={t(`scientist_resonance.secondary.${index === 0 ? "a" : "b"}`)}
                      dossierLabel={t("scientist_resonance.hover.dossier")}
                      achievementsLabel={t("scientist_resonance.hover.achievements")}
                    />
                  ))}
                </div>
              ) : null}
            </div>
          ) : activeTab === "recent_state" ? (
            <div className="flex min-h-[340px] flex-col items-center justify-center rounded-[24px] border border-dashed border-[var(--border)]/70 bg-[linear-gradient(135deg,rgba(236,231,221,0.38),rgba(255,255,255,0.7))] px-6 text-center">
              <div className="rounded-full border border-[var(--border)]/70 bg-[var(--card)]/90 p-3 shadow-sm">
                <Sparkles className="h-5 w-5 text-[var(--primary)]" />
              </div>
              <p className="mt-5 font-serif text-[24px] text-[var(--foreground)]">
                {t("scientist_resonance.empty.recent_title")}
              </p>
              <p className="mt-3 max-w-md text-[13px] leading-7 text-[var(--muted-foreground)]">
                {t("scientist_resonance.empty.recent_body")}
              </p>
            </div>
          ) : (
            <div className="flex min-h-[340px] items-center justify-center rounded-[24px] border border-dashed border-[var(--border)]/70 bg-[var(--muted)]/30 px-6 text-center text-[13px] text-[var(--muted-foreground)]">
              {t("scientist_resonance.empty.long_term")}
            </div>
          )}

          {refreshing ? (
            <div className="absolute inset-0 z-30 hidden items-center justify-center md:flex">
              <div className="absolute inset-0 rounded-[26px] bg-[rgba(250,249,246,0.64)] backdrop-blur-[2px]" />
              <div className="relative flex w-[440px] flex-col items-center rounded-[26px] border border-[rgba(176,80,30,0.18)] bg-[rgba(255,252,247,0.96)] px-7 py-6 text-center shadow-[0_30px_80px_rgba(37,29,21,0.14)]">
                <div className="flex h-12 w-12 items-center justify-center rounded-full border border-[rgba(176,80,30,0.18)] bg-[rgba(176,80,30,0.10)]">
                  <Loader2 className="h-5 w-5 animate-spin text-[var(--primary)]" />
                </div>
                <p className="mt-4 text-[10px] uppercase tracking-[0.22em] text-[var(--primary)]">
                  {t("scientist_resonance.loading.kicker")}
                </p>
                <p className="mt-3 font-serif text-[24px] leading-9 tracking-[-0.02em] text-[var(--foreground)]">
                  {activeLoadingCopy || t("scientist_resonance.loading.fallback")}
                </p>
                <p className="mt-3 text-[12px] leading-6 text-[var(--muted-foreground)]">
                  {t("scientist_resonance.loading.subtitle")}
                </p>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
