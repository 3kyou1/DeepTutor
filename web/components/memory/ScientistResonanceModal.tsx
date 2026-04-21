"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCw, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

import Modal from "@/components/common/Modal";
import {
  getScientistResonance,
  regenerateScientistResonance,
  type ScientistResonanceCard,
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

function CardView({
  card,
  cardLabel,
  whyLabel,
  confidenceLabel,
}: {
  card: ScientistResonanceCard;
  cardLabel: string;
  whyLabel: string;
  confidenceLabel: string;
}) {
  return (
    <div className="relative overflow-hidden rounded-[30px] border border-[var(--border)]/70 bg-[var(--card)] shadow-[0_24px_80px_rgba(37,29,21,0.08)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(176,80,30,0.12),transparent_34%),linear-gradient(135deg,rgba(236,231,221,0.55),transparent_48%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(176,80,30,0.45),transparent)]" />

      <div className="relative grid gap-6 p-5 md:grid-cols-[280px_minmax(0,1fr)] md:p-7">
        <div className="relative">
          <div className="absolute inset-x-4 -top-3 z-10 rounded-full border border-[var(--border)]/60 bg-[var(--background)]/90 px-3 py-1 text-center text-[10px] uppercase tracking-[0.24em] text-[var(--muted-foreground)] backdrop-blur">
            {cardLabel}
          </div>
          <div className="relative overflow-hidden rounded-[26px] border border-[var(--border)]/70 bg-[linear-gradient(180deg,rgba(236,231,221,0.95),rgba(250,249,246,0.6))] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
            <div className="relative overflow-hidden rounded-[20px] border border-[var(--border)]/70 bg-[#d9d2c7]">
              <div className="pointer-events-none absolute inset-0 z-10 bg-[linear-gradient(180deg,transparent,rgba(0,0,0,0.16))]" />
              <Image
                src={card.portrait_url}
                alt={card.name}
                width={512}
                height={512}
                className="h-auto w-full object-cover grayscale transition-transform duration-700 hover:scale-[1.03]"
                priority={false}
              />
            </div>
            <div className="mt-3 flex items-center justify-between gap-3 px-1">
              <div className="min-w-0">
                <p className="font-serif text-[16px] leading-none tracking-[0.02em] text-[var(--foreground)]">
                  {card.name}
                </p>
                <p className="mt-1 text-[10px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                  {confidenceLabel}
                </p>
              </div>
              <div className="h-9 w-9 rounded-full border border-[var(--border)]/70 bg-[var(--background)]/90 shadow-sm" />
            </div>
          </div>
        </div>

        <div className="relative min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-[0.28em] text-[var(--muted-foreground)]">
                {cardLabel}
              </p>
              <h3 className="mt-3 max-w-2xl font-serif text-[34px] leading-[1.02] tracking-[-0.03em] text-[var(--foreground)] md:text-[42px]">
                {card.name}
              </h3>
            </div>
            <div className="rounded-full border border-[rgba(176,80,30,0.18)] bg-[rgba(176,80,30,0.08)] px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-[var(--primary)]">
              {confidenceLabel}
            </div>
          </div>

          <p className="mt-4 max-w-2xl font-serif text-[18px] italic leading-8 text-[var(--muted-foreground)] md:text-[19px]">
            {card.hook}
          </p>

          <div className="mt-6 rounded-[24px] border border-[var(--border)]/70 bg-[linear-gradient(135deg,rgba(236,231,221,0.68),rgba(255,255,255,0.72))] px-5 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
            <div className="mb-4 h-px w-14 bg-[var(--primary)]/45" />
            <p className="max-w-2xl font-serif text-[22px] leading-9 tracking-[-0.01em] text-[var(--foreground)] md:text-[24px]">
              “{card.quote_zh}”
            </p>
            {card.quote_en ? (
              <p className="mt-3 max-w-2xl text-[12px] uppercase tracking-[0.08em] text-[var(--muted-foreground)]/90">
                {card.quote_en}
              </p>
            ) : null}
          </div>

          <div className="mt-6 rounded-[24px] border border-[var(--border)]/70 bg-[var(--background)]/85 px-5 py-4">
            <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
              {whyLabel}
            </p>
            <p className="mt-3 max-w-2xl text-[15px] leading-8 text-[var(--foreground)]">
              {card.reason}
            </p>
          </div>

          {card.resonance_axes.length > 0 ? (
            <div className="mt-6 flex flex-wrap gap-2.5">
              {card.resonance_axes.map((axis) => (
                <span
                  key={axis}
                  className="rounded-full border border-[var(--border)]/70 bg-[var(--card)] px-3.5 py-1.5 text-[11px] uppercase tracking-[0.12em] text-[var(--muted-foreground)] shadow-[0_6px_18px_rgba(37,29,21,0.04)]"
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

  const currentCard = useMemo(
    () => (activeTab === "long_term" ? payload.long_term : payload.recent_state),
    [activeTab, payload.long_term, payload.recent_state],
  );

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
      <div className="bg-[linear-gradient(180deg,rgba(250,249,246,0.85),transparent_24%)] px-5 py-4">
        <div className="relative overflow-hidden rounded-[28px] border border-[var(--border)]/70 bg-[linear-gradient(135deg,rgba(255,255,255,0.96),rgba(236,231,221,0.75))] px-5 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
          <div className="pointer-events-none absolute right-[-4rem] top-[-4rem] h-36 w-36 rounded-full bg-[rgba(176,80,30,0.10)] blur-3xl" />
          <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="max-w-xl">
              <p className="text-[11px] uppercase tracking-[0.28em] text-[var(--primary)]">
                {t("scientist_resonance.modal.kicker")}
              </p>
              <p className="mt-3 max-w-lg text-[14px] leading-7 text-[var(--muted-foreground)]">
                {t("scientist_resonance.modal.subtitle")}
              </p>
            </div>

            <div className="inline-flex rounded-2xl border border-[var(--border)]/70 bg-[var(--background)]/80 p-1.5 shadow-sm backdrop-blur">
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
                    className={`rounded-xl px-3.5 py-2 text-[12px] transition-all ${
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

        <div className="mt-5 min-h-[420px]">
          {loading ? (
            <div className="flex min-h-[420px] items-center justify-center rounded-[28px] border border-[var(--border)]/70 bg-[var(--muted)]/25">
              <Loader2 className="h-5 w-5 animate-spin text-[var(--primary)]" />
            </div>
          ) : currentCard ? (
            <CardView
              card={currentCard}
              cardLabel={t("scientist_resonance.card.label")}
              whyLabel={t("scientist_resonance.card.why")}
              confidenceLabel={
                currentCard.confidence_style === "strong_resonance"
                  ? t("scientist_resonance.card.confidence.strong")
                  : t("scientist_resonance.card.confidence.phase")
              }
            />
          ) : activeTab === "recent_state" ? (
            <div className="flex min-h-[420px] flex-col items-center justify-center rounded-[28px] border border-dashed border-[var(--border)]/70 bg-[linear-gradient(135deg,rgba(236,231,221,0.38),rgba(255,255,255,0.7))] px-6 text-center">
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
            <div className="flex min-h-[420px] items-center justify-center rounded-[28px] border border-dashed border-[var(--border)]/70 bg-[var(--muted)]/30 px-6 text-center text-[13px] text-[var(--muted-foreground)]">
              {t("scientist_resonance.empty.long_term")}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
