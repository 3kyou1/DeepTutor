"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, SlidersHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";

import Modal from "@/components/common/Modal";
import {
  listColdStartQuestions,
  submitColdStartAnswers,
  type ColdStartQuestionsResponse,
} from "@/lib/personalization-api";

interface CopaColdStartModalProps {
  isOpen: boolean;
  language: string;
  onClose: () => void;
  onSubmitted: () => Promise<void> | void;
}

const EMPTY_QUESTIONS: ColdStartQuestionsResponse = {
  questions: [],
  scale: [],
  question_count: 0,
};

export default function CopaColdStartModal({
  isOpen,
  language,
  onClose,
  onSubmitted,
}: CopaColdStartModalProps) {
  const { t } = useTranslation();
  const [payload, setPayload] = useState<ColdStartQuestionsResponse>(EMPTY_QUESTIONS);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isOpen) {
      setAnswers({});
      setError("");
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const next = await listColdStartQuestions(language);
        if (!cancelled) setPayload(next);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("Unknown error"));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [isOpen, language, t]);

  const answeredCount = useMemo(
    () => Object.values(answers).filter((value) => Number.isInteger(value) && value >= 1 && value <= 5).length,
    [answers],
  );

  const total = payload.question_count || payload.questions.length;
  const canSubmit = total > 0 && answeredCount === total && !loading && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError("");
    try {
      await submitColdStartAnswers(language, answers);
      await onSubmitted();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Unknown error"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={submitting ? () => undefined : onClose}
      title={t("copa_cold_start.modal.title")}
      titleIcon={<SlidersHorizontal className="h-4 w-4" />}
      width="xl"
      closeOnBackdrop={!submitting}
    >
      <div className="px-5 py-4">
        <p className="mb-4 text-[13px] text-[var(--muted-foreground)]">
          {t("copa_cold_start.modal.scale_hint")}
        </p>

        {loading ? (
          <div className="flex min-h-[320px] items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-[var(--muted-foreground)]" />
          </div>
        ) : (
          <div className="space-y-3">
            {payload.questions.map((question) => (
              <div
                key={question.id}
                className="rounded-xl border border-[var(--border)]/70 px-4 py-3"
              >
                <div className="mb-3 flex items-start justify-between gap-3">
                  <p className="text-[13px] font-medium text-[var(--foreground)]">
                    {question.order}. {question.prompt}
                  </p>
                  <span className="rounded-full bg-[var(--muted)] px-2 py-0.5 text-[11px] text-[var(--muted-foreground)]">
                    {question.factor}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {payload.scale.map((option) => {
                    const selected = answers[question.id] === option.value;
                    return (
                      <button
                        key={`${question.id}-${option.value}`}
                        type="button"
                        disabled={submitting}
                        onClick={() => setAnswers((prev) => ({ ...prev, [question.id]: option.value }))}
                        className={`min-w-[72px] rounded-lg border px-3 py-2 text-[12px] transition-colors ${
                          selected
                            ? "border-[var(--foreground)] bg-[var(--foreground)] text-[var(--background)]"
                            : "border-[var(--border)]/70 text-[var(--muted-foreground)] hover:border-[var(--border)] hover:text-[var(--foreground)]"
                        } ${submitting ? "opacity-60" : ""}`}
                      >
                        <div className="font-medium">{option.value}</div>
                        <div className="mt-0.5 text-[10px]">{option.label}</div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 flex items-center justify-between gap-3">
          <div className="text-[12px] text-[var(--muted-foreground)]">
            {t("copa_cold_start.modal.progress", {
              answered: answeredCount,
              total,
            })}
          </div>
          {error ? <div className="text-[12px] text-red-500">{error}</div> : null}
        </div>
      </div>

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          disabled={submitting}
          className="rounded-lg border border-[var(--border)]/70 px-3 py-2 text-[13px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)] disabled:opacity-50"
        >
          {t("copa_cold_start.modal.cancel")}
        </button>
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={!canSubmit}
          className="rounded-lg bg-[var(--foreground)] px-3 py-2 text-[13px] font-medium text-[var(--background)] transition-opacity disabled:opacity-40"
        >
          {submitting ? t("copa_cold_start.modal.submitting") : t("copa_cold_start.modal.submit")}
        </button>
      </div>
    </Modal>
  );
}
