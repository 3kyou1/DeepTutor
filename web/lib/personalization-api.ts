import { apiUrl } from "@/lib/api";

export interface ColdStartQuestion {
  id: string;
  factor: string;
  order: number;
  prompt: string;
}

export interface ColdStartScaleOption {
  value: number;
  label: string;
}

export interface ColdStartQuestionsResponse {
  questions: ColdStartQuestion[];
  scale: ColdStartScaleOption[];
  question_count: number;
}

export interface ColdStartStatus {
  profile_source: string | null;
  has_cold_start_profile: boolean;
  live_rebuild_threshold: number;
  real_user_messages: number;
  completed_at: string | null;
  can_reinitialize: boolean;
}

export interface ColdStartSubmitResponse {
  profile_source: string;
  profile_updated: boolean;
  completed_at: string;
  factor_scores: Record<string, number>;
  profile_preview: string;
}

async function parseJsonOrThrow(response: Response) {
  if (response.ok) return response.json();
  let detail = "Request failed";
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string" && payload.detail) {
      detail = payload.detail;
    }
  } catch {
    // ignore malformed json
  }
  throw new Error(detail);
}

export async function listColdStartQuestions(language: string): Promise<ColdStartQuestionsResponse> {
  const response = await fetch(
    apiUrl(`/api/v1/personalization/cold-start/questions?language=${encodeURIComponent(language)}`),
    { cache: "no-store" },
  );
  return parseJsonOrThrow(response);
}

export async function getColdStartStatus(): Promise<ColdStartStatus> {
  const response = await fetch(apiUrl("/api/v1/personalization/cold-start/status"), {
    cache: "no-store",
  });
  return parseJsonOrThrow(response);
}

export async function submitColdStartAnswers(
  language: string,
  answers: Record<string, number>,
): Promise<ColdStartSubmitResponse> {
  const response = await fetch(apiUrl("/api/v1/personalization/cold-start/submit"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language, answers }),
  });
  return parseJsonOrThrow(response);
}
