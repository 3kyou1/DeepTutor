import type { ProfileImportApplyResponse } from "@/lib/personalization-api";

export interface ProfileImportApplyStatus {
  updatedSections: string[];
  profileUpdatedAt: string | null;
}

export interface ProfileImportApplyAvailability {
  canApply: boolean;
  applying: boolean;
  applied: boolean;
}

export function toProfileImportApplyStatus(
  result: Pick<ProfileImportApplyResponse, "updated_sections" | "profile_updated_at">,
): ProfileImportApplyStatus {
  return {
    updatedSections: [...result.updated_sections],
    profileUpdatedAt: result.profile_updated_at,
  };
}

export function canApplyProfileImport(
  input: ProfileImportApplyAvailability,
): boolean {
  return input.canApply && !input.applying && !input.applied;
}
