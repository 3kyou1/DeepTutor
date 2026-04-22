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

export type ProfileImportMode = "create" | "merge" | "overwrite";
export type ProfileImportSourceType = "folder" | "pasted_text";
export type ProfileImportProvider = "codex" | "claude_code" | "cursor";

export interface ProfileImportRequest {
  mode: ProfileImportMode;
  language: string;
  source_type: ProfileImportSourceType;
  provider?: ProfileImportProvider | null;
  folder_path?: string | null;
  text: string;
}

export interface ProfileImportUploadItem {
  file: File;
  relative_path: string;
}

export interface ProfileImportUploadRequest {
  mode: ProfileImportMode;
  language: string;
  provider: ProfileImportProvider;
  files: ProfileImportUploadItem[];
}

export interface ProfileImportPreviewResponse {
  mode: ProfileImportMode;
  source_type: ProfileImportSourceType;
  provider: ProfileImportProvider | null;
  detected_turns: number;
  extracted_user_messages: string[];
  effective_signal_count: number;
  warnings: string[];
  generated_copa_markdown: string;
  generated_summary_markdown: string;
  will_update_sections: string[];
  can_apply: boolean;
  scanned_session_count: number;
}

export interface ProfileImportApplyResponse {
  applied: boolean;
  mode: ProfileImportMode;
  warnings: string[];
  updated_sections: string[];
  profile_updated_at: string | null;
  profile: string;
}

export interface ScientistResonanceCard {
  name: string;
  slug: string;
  portrait_url: string;
  hook: string;
  quote_zh: string;
  quote_en: string;
  reason: string;
  resonance_axes: string[];
  confidence_style: "strong_resonance" | "phase_resonance";
  loading_copy_zh: string;
  loading_copy_en: string;
  bio_zh: string;
  bio_en: string;
  achievements_zh: string[];
  achievements_en: string[];
}

export interface ScientistResonanceLongTermResult {
  primary: ScientistResonanceCard;
  secondary: ScientistResonanceCard[];
}

export interface ScientistResonanceResponse {
  long_term: ScientistResonanceLongTermResult | null;
  recent_state: ScientistResonanceCard | null;
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

export async function previewProfileImport(
  payload: ProfileImportRequest,
): Promise<ProfileImportPreviewResponse> {
  const response = await fetch(apiUrl("/api/v1/personalization/profile-import/preview"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow(response);
}

export async function applyProfileImport(
  payload: ProfileImportRequest,
): Promise<ProfileImportApplyResponse> {
  const response = await fetch(apiUrl("/api/v1/personalization/profile-import/apply"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow(response);
}

function buildProfileImportUploadFormData(payload: ProfileImportUploadRequest): FormData {
  const formData = new FormData();
  formData.append("mode", payload.mode);
  formData.append("language", payload.language);
  formData.append("provider", payload.provider);
  for (const item of payload.files) {
    formData.append("files", item.file);
    formData.append("relative_paths", item.relative_path);
  }
  return formData;
}

export async function previewProfileImportUpload(
  payload: ProfileImportUploadRequest,
): Promise<ProfileImportPreviewResponse> {
  const response = await fetch(apiUrl("/api/v1/personalization/profile-import/preview-upload"), {
    method: "POST",
    body: buildProfileImportUploadFormData(payload),
  });
  return parseJsonOrThrow(response);
}

export async function applyProfileImportUpload(
  payload: ProfileImportUploadRequest,
): Promise<ProfileImportApplyResponse> {
  const response = await fetch(apiUrl("/api/v1/personalization/profile-import/apply-upload"), {
    method: "POST",
    body: buildProfileImportUploadFormData(payload),
  });
  return parseJsonOrThrow(response);
}

export async function getScientistResonance(language: string): Promise<ScientistResonanceResponse> {
  const response = await fetch(
    apiUrl(`/api/v1/personalization/scientist-resonance?language=${encodeURIComponent(language)}`),
    { cache: "no-store" },
  );
  return parseJsonOrThrow(response);
}

export async function regenerateScientistResonance(
  language: string,
  mode: "long_term" | "recent_state" | "both" = "both",
): Promise<ScientistResonanceResponse> {
  const response = await fetch(apiUrl("/api/v1/personalization/scientist-resonance/regenerate"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language, mode }),
  });
  return parseJsonOrThrow(response);
}
