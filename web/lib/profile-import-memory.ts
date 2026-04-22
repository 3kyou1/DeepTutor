import type { ProfileImportApplyResponse } from "@/lib/personalization-api";

export interface MemoryPageState {
  summary: string;
  profile: string;
  summary_updated_at: string | null;
  profile_updated_at: string | null;
}

export interface MemoryPageEditors {
  summary: string;
  profile: string;
}

export function applyImportedProfileToMemoryState(
  data: MemoryPageState,
  editors: MemoryPageEditors,
  result: Pick<ProfileImportApplyResponse, "profile" | "profile_updated_at">,
): { data: MemoryPageState; editors: MemoryPageEditors } {
  return {
    data: {
      ...data,
      profile: result.profile,
      profile_updated_at: result.profile_updated_at,
    },
    editors: {
      ...editors,
      profile: result.profile,
    },
  };
}
